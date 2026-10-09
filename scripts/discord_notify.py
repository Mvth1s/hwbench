#!/usr/bin/env python3
"""Notifications Discord des workflows GitHub Actions (bibliothèque standard uniquement).

Usage : python3 scripts/discord_notify.py COMMANDE [options]   (voir --help)

Chaque commande construit un ou plusieurs messages (fonctions pures, testées dans
tests/test_discord_notify.py) puis les envoie au webhook lu dans une variable d'environnement
fixe par commande (DISCORD_WEBHOOK_CI, DISCORD_WEBHOOK_CLASSEMENT…), alimentée par un secret.

Règles :
- jamais d'échec du job : secret absent, API injoignable ou refus de Discord donnent un
  avertissement (::warning::) et le code de retour 0 ;
- l'URL du webhook n'est jamais affichée (ni dans les avertissements, ni dans les exceptions) ;
- allowed_mentions vide sur chaque message : aucun @everyone, rôle ou utilisateur notifié ;
- tout texte venu d'un contributeur ou d'un service externe (titre de PR, nom de machine,
  message de commit, annotation) est échappé (Markdown) et tronqué aux limites de Discord ;
- les données des workflow_run viennent de l'événement (GITHUB_EVENT_PATH) et de l'API GitHub,
  jamais du code de la PR.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

USER_AGENT = "hwbench-notify (https://github.com/Mvth1s/hwbench, 1.0)"
PACKAGE = "hwbench"

# Limites de Discord (https://discord.com/developers/docs/resources/message#embed-object-embed-limits)
TITLE_MAX = 256
DESCRIPTION_MAX = 4096
FIELDS_MAX = 25
FIELD_NAME_MAX = 256
FIELD_VALUE_MAX = 1024
FOOTER_MAX = 2048
EMBED_TOTAL_MAX = 6000  # somme des textes de tous les embeds d'un message
EMBEDS_PER_MESSAGE = 10
URL_MAX = 2048

RED = 0xCF222E
GREEN = 0x1A7F37
BLUE = 0x0969DA
AMBER = 0x9A6700

FAILED = frozenset({"failure", "timed_out", "startup_failure"})
WATCHED_BRANCHES = ("dev", "main")
RETRY_AFTER_MAX = 60.0

Payload = dict[str, Any]
Api = Callable[[str], Any]


# --- Texte -------------------------------------------------------------------------------------


def truncate(text: str, limit: int) -> str:
    """Texte coupé à `limit` caractères, « … » final compris."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


_MD_SPECIAL = re.compile(r"([\\`*_~|>\[\]()#<:@-])")


def escape_md(text: object) -> str:
    """Texte externe affiché tel quel : Markdown, liens masqués et mentions neutralisés."""
    return _MD_SPECIAL.sub(r"\\\1", str(text))


def first_line(text: str | None) -> str:
    return (text or "").strip().splitlines()[0] if (text or "").strip() else ""


def fr_int(value: int) -> str:
    """Entier avec espaces fines insécables comme séparateur de milliers (règle de fmt.py)."""
    return f"{value:,}".replace(",", " ")


def fr_date(iso: str | None) -> str:
    """Date ISO 8601 -> JJ/MM/AAAA ; la valeur brute si elle est illisible."""
    if not iso:
        return "inconnue"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        return iso


def link(label: str, url: str | None) -> str:
    """Lien masqué ; `label` doit déjà être échappé. Sans URL https, le texte seul."""
    if not url or not url.startswith("https://") or len(url) > URL_MAX:
        return label
    return f"[{label}]({url})"


# --- Messages ----------------------------------------------------------------------------------


def field(name: str, value: str, inline: bool = False) -> dict[str, Any]:
    return {
        "name": truncate(name, FIELD_NAME_MAX) or "​",
        "value": truncate(value, FIELD_VALUE_MAX) or "​",
        "inline": inline,
    }


def _embed_size(embed: dict[str, Any]) -> int:
    size = len(embed.get("title", "")) + len(embed.get("description", ""))
    size += len(embed.get("footer", {}).get("text", ""))
    return size + sum(len(f["name"]) + len(f["value"]) for f in embed.get("fields", []))


def embed(
    title: str,
    description: str = "",
    *,
    url: str | None = None,
    color: int = BLUE,
    fields: Iterable[dict[str, Any]] = (),
    footer: str | None = None,
) -> dict[str, Any]:
    """Embed Discord dont chaque texte respecte les limites ; le total est borné à 6000."""
    out: dict[str, Any] = {"title": truncate(title, TITLE_MAX), "color": color}
    if description:
        out["description"] = truncate(description, DESCRIPTION_MAX)
    if url and url.startswith("https://") and len(url) <= URL_MAX:
        out["url"] = url
    fields = list(fields)[:FIELDS_MAX]
    if fields:
        out["fields"] = fields
    if footer:
        out["footer"] = {"text": truncate(footer, FOOTER_MAX)}
    # au-delà du total : on retire les derniers champs, puis on raccourcit la description
    while _embed_size(out) > EMBED_TOTAL_MAX and out.get("fields"):
        out["fields"].pop()
    excess = _embed_size(out) - EMBED_TOTAL_MAX
    if excess > 0 and out.get("description"):
        out["description"] = truncate(out["description"], len(out["description"]) - excess)
    return out


def payloads(embeds: list[dict[str, Any]]) -> list[Payload]:
    """Messages prêts à envoyer : au plus 10 embeds et 6000 caractères chacun, aucune mention."""
    messages: list[Payload] = []
    batch: list[dict[str, Any]] = []
    for item in embeds:
        size = sum(_embed_size(e) for e in batch) + _embed_size(item)
        if batch and (len(batch) == EMBEDS_PER_MESSAGE or size > EMBED_TOTAL_MAX):
            messages.append(_payload(batch))
            batch = []
        batch.append(item)
    if batch:
        messages.append(_payload(batch))
    return messages


def _payload(embeds: list[dict[str, Any]]) -> Payload:
    return {"embeds": embeds, "allowed_mentions": {"parse": []}}


# --- Envoi -------------------------------------------------------------------------------------


def _workflow_command(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def warn(message: str) -> None:
    """Avertissement visible dans le résumé du run, sans faire échouer le job."""
    print(f"::warning title=Notification Discord::{_workflow_command(message)}", flush=True)


def _retry_after(exc: HTTPError) -> float:
    """Délai demandé par Discord sur un 429 (corps JSON retry_after, sinon Retry-After)."""
    delay: float | None = None
    try:
        delay = float(json.loads(exc.read().decode() or "{}")["retry_after"])
    except (ValueError, KeyError, TypeError, OSError, AttributeError):
        header = exc.headers.get("Retry-After") if exc.headers else None
        try:
            delay = float(header) if header is not None else None
        except ValueError:
            delay = None
    return min(max(delay if delay is not None else 1.0, 0.0), RETRY_AFTER_MAX)


def send(
    url: str,
    payload: Payload,
    *,
    opener: Callable[..., Any] = urlopen,
    sleep: Callable[[float], None] = time.sleep,
    attempts: int = 4,
) -> bool:
    """POST du message. Le texte des exceptions n'est jamais affiché (il pourrait citer l'URL)."""
    data = json.dumps(payload, ensure_ascii=False).encode()
    for attempt in range(1, attempts + 1):
        request = Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with opener(request, timeout=30):
                return True
        except HTTPError as exc:
            if exc.code == 429 and attempt < attempts:
                sleep(_retry_after(exc))
                continue
            warn(f"Discord a refusé le message (HTTP {exc.code})")
            return False
        except (URLError, OSError, ValueError) as exc:
            warn(f"envoi impossible ({type(exc).__name__})")
            return False
    return False


def deliver(webhook_env: str, messages: list[Payload], **send_options: Any) -> None:
    url = os.environ.get(webhook_env, "").strip()
    if not url:
        warn(f"secret {webhook_env} absent : notification ignorée")
        return
    for message in messages:
        send(url, message, **send_options)


# --- Accès aux API (les seules fonctions qui touchent le réseau, hors send) --------------------


def fetch_json(url: str, headers: dict[str, str] | None = None) -> Any:
    request = Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def github_api(path: str) -> Any:
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return fetch_json(base + path, headers)


def read_event() -> dict[str, Any]:
    return json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))


# --- #ci : échec sur dev ou main, retour au vert -----------------------------------------------


def _commit_line(run: dict[str, Any]) -> str:
    sha = (run.get("head_sha") or "")[:7]
    message = escape_md(truncate(first_line((run.get("head_commit") or {}).get("message")), 200))
    return f"`{sha}` {message}".strip()


def ci_failure_embed(run: dict[str, Any], failed_jobs: list[dict[str, Any]]) -> dict[str, Any]:
    branch = run.get("head_branch", "?")
    jobs = "\n".join(
        f"• {link(escape_md(job.get('name', '?')), job.get('html_url'))}" for job in failed_jobs
    )
    return embed(
        f"{run.get('name', 'Workflow')} en échec sur {branch}",
        _commit_line(run),
        url=run.get("html_url"),
        color=RED,
        fields=[field("Jobs en échec", jobs or "aucun job identifié, voir le run")],
    )


def ci_recovered_embed(run: dict[str, Any]) -> dict[str, Any]:
    return embed(
        f"{run.get('name', 'Workflow')} de nouveau au vert sur {run.get('head_branch', '?')}",
        _commit_line(run),
        url=run.get("html_url"),
        color=GREEN,
    )


def previous_conclusion(runs: list[dict[str, Any]], current: dict[str, Any]) -> str | None:
    """Conclusion du dernier run terminé (succès ou échec) avant `current`, annulés ignorés."""
    earlier = [
        r
        for r in runs
        if r.get("id") != current.get("id")
        and (r.get("created_at") or "") < (current.get("created_at") or "")
        and (r.get("conclusion") in FAILED or r.get("conclusion") == "success")
    ]
    if not earlier:
        return None
    return max(earlier, key=lambda r: r.get("created_at") or "")["conclusion"]


def is_watched_push(event: dict[str, Any]) -> bool:
    run = event.get("workflow_run") or {}
    return (
        run.get("event") == "push"
        and run.get("head_branch") in WATCHED_BRANCHES
        and (run.get("head_repository") or {}).get("full_name")
        == (event.get("repository") or {}).get("full_name")
    )


def ci_messages(event: dict[str, Any], api: Api) -> list[dict[str, Any]]:
    if not is_watched_push(event):
        return []
    run = event["workflow_run"]
    repo = event["repository"]["full_name"]
    conclusion = run.get("conclusion")
    if conclusion in FAILED:
        jobs = api(f"/repos/{repo}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100")
        failed = [job for job in jobs.get("jobs", []) if job.get("conclusion") in FAILED]
        return [ci_failure_embed(run, failed)]
    if conclusion != "success":
        return []
    attempt = int(run.get("run_attempt") or 1)
    if attempt > 1:
        # relance d'un run : l'essai précédent du même run compte comme le run précédent
        prior = api(f"/repos/{repo}/actions/runs/{run['id']}/attempts/{attempt - 1}")
        previous = prior.get("conclusion")
    else:
        branch = quote(run["head_branch"], safe="")
        runs = api(
            f"/repos/{repo}/actions/workflows/{run['workflow_id']}/runs"
            f"?branch={branch}&event=push&status=completed&per_page=20"
        )
        previous = previous_conclusion(runs.get("workflow_runs", []), run)
    return [ci_recovered_embed(run)] if previous in FAILED else []


# --- PR d'un workflow_run (y compris depuis un fork, où pull_requests est vide) ----------------


def find_pull_request(event: dict[str, Any], api: Api) -> dict[str, Any] | None:
    run = event["workflow_run"]
    repo = event["repository"]["full_name"]
    if run.get("pull_requests"):
        return api(f"/repos/{repo}/pulls/{int(run['pull_requests'][0]['number'])}")
    owner = ((run.get("head_repository") or {}).get("owner") or {}).get("login")
    branch = run.get("head_branch")
    if not owner or not branch:
        return None
    head = quote(f"{owner}:{branch}", safe="")
    pulls = api(f"/repos/{repo}/pulls?state=all&head={head}&per_page=10")
    return next((p for p in pulls if (p.get("head") or {}).get("sha") == run.get("head_sha")), None)


def _pr_line(run: dict[str, Any], pr: dict[str, Any] | None) -> str:
    title = escape_md(truncate(pr.get("title") if pr else run.get("display_title") or "", 200))
    if not pr:
        return title or "pull request introuvable"
    return link(f"\\#{int(pr['number'])} {title}", pr.get("html_url"))


# --- #classement : soumission validée ou refusée -----------------------------------------------

EXIT_CODE_ANNOTATION = re.compile(r"^Process completed with exit code \d+\.?$")


def refusal_reasons(event: dict[str, Any], api: Api, limit: int = 10) -> list[str]:
    """Raisons d'un refus : annotations d'erreur des jobs en échec, sinon les étapes en échec."""
    run = event["workflow_run"]
    repo = event["repository"]["full_name"]
    jobs = api(f"/repos/{repo}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100")
    reasons: list[str] = []
    for job in jobs.get("jobs", []):
        if job.get("conclusion") not in FAILED:
            continue
        annotations = api(f"/repos/{repo}/check-runs/{int(job['id'])}/annotations?per_page=50")
        for annotation in annotations:
            message = (annotation.get("message") or "").strip()
            failure = annotation.get("annotation_level") == "failure"
            if failure and message and not EXIT_CODE_ANNOTATION.match(message):
                reasons.append(message)
        if not reasons:
            reasons += [
                f"étape en échec : {step.get('name', '?')}"
                for step in job.get("steps", [])
                if step.get("conclusion") in FAILED
            ]
    return reasons[:limit]


def results_embed(
    run: dict[str, Any], pr: dict[str, Any] | None, reasons: list[str]
) -> dict[str, Any]:
    author = ((pr or {}).get("user") or {}).get("login") or (run.get("actor") or {}).get("login")
    fields = [field("Auteur", escape_md(author), inline=True)] if author else []
    if run.get("conclusion") == "success":
        return embed(
            "Soumission au classement validée",
            _pr_line(run, pr),
            url=(pr or {}).get("html_url") or run.get("html_url"),
            color=GREEN,
            fields=fields,
        )
    listed = "\n".join(f"• {escape_md(truncate(r, 300))}" for r in reasons)
    fields.append(field("Raisons", listed or "voir le run de validation"))
    fields.append(field("Run", link("journal de validation", run.get("html_url"))))
    return embed(
        "Soumission au classement refusée",
        _pr_line(run, pr),
        url=(pr or {}).get("html_url") or run.get("html_url"),
        color=RED,
        fields=fields,
    )


def results_messages(event: dict[str, Any], api: Api) -> list[dict[str, Any]]:
    run = event.get("workflow_run") or {}
    if run.get("event") != "pull_request" or run.get("conclusion") not in FAILED | {"success"}:
        return []
    reasons = refusal_reasons(event, api) if run["conclusion"] in FAILED else []
    return [results_embed(run, find_pull_request(event, api), reasons)]


# --- #dependabot : CI des PR de dependabot[bot] ------------------------------------------------

DEPENDABOT = "dependabot[bot]"


def dependabot_embed(run: dict[str, Any], pr: dict[str, Any] | None) -> dict[str, Any]:
    ok = run.get("conclusion") == "success"
    return embed(
        f"PR Dependabot : {run.get('name', 'CI')} {'réussie' if ok else 'en échec'}",
        _pr_line(run, pr),
        url=(pr or {}).get("html_url") or run.get("html_url"),
        color=GREEN if ok else RED,
        fields=[field("Run", link("détails", run.get("html_url")))],
    )


def dependabot_messages(event: dict[str, Any], api: Api) -> list[dict[str, Any]]:
    run = event.get("workflow_run") or {}
    if run.get("event") != "pull_request" or (run.get("actor") or {}).get("login") != DEPENDABOT:
        return []
    if run.get("conclusion") not in FAILED | {"success"}:
        return []
    return [dependabot_embed(run, find_pull_request(event, api))]


# --- #releases et #deploiements (release.yml) --------------------------------------------------

_COMMIT_REF = re.compile(r"\s*\(\[`[0-9a-f]{7,40}`\]\([^)\s]*\)\)")


def changelog_excerpt(body: str, limit: int = 1500) -> str:
    """Notes de la GitHub Release sans le titre de version ni les liens de commit, coupées sur
    une fin de ligne."""
    lines = [line for line in _COMMIT_REF.sub("", body or "").splitlines()]
    if lines and lines[0].startswith("## "):
        lines = lines[1:]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    # « ### Bug Fixes » s'affiche en gros titre dans un embed : en gras, plus compact
    text = re.sub(r"^#{1,6}\s+(.+)$", r"**\1**", text, flags=re.MULTILINE)
    if len(text) <= limit:
        return text
    cut = text.rfind("\n", 0, limit - 2)
    return text[: cut if cut > 0 else limit - 2].rstrip() + "\n…"


def verify_command(version: str, repo: str) -> str:
    wheel = f"{PACKAGE}-{version}-py3-none-any.whl"
    return (
        "```sh\n"
        f"pip download {PACKAGE}=={version} --no-deps\n"
        f"gh attestation verify {wheel} --repo {repo}\n"
        "```"
    )


def release_embed(release: dict[str, Any], repo: str) -> dict[str, Any]:
    tag = release.get("tag_name", "")
    version = tag.removeprefix("v")
    pypi = f"https://pypi.org/project/{PACKAGE}/{version}/"
    return embed(
        f"{PACKAGE} {version} publiée",
        changelog_excerpt(release.get("body") or "") or "Pas de notes de version.",
        url=release.get("html_url"),
        color=BLUE,
        fields=[
            field("PyPI", f"{link('pypi.org', pypi)} (après approbation de la publication)"),
            field("Vérifier la provenance", verify_command(version, repo)),
        ],
    )


def pypi_pending_embed(version: str, run_url: str) -> dict[str, Any]:
    return embed(
        f"PyPI : {PACKAGE} {version} en attente d'approbation",
        f"La publication attend l'approbation de l'environnement « pypi » : {link('run', run_url)}",
        url=run_url,
        color=AMBER,
    )


def pypi_published_embed(version: str) -> dict[str, Any]:
    url = f"https://pypi.org/project/{PACKAGE}/{version}/"
    return embed(
        f"{PACKAGE} {version} publié sur PyPI",
        f"`pipx install {PACKAGE}=={version}`",
        url=url,
        color=GREEN,
    )


# --- pages.yml : déploiement et nouvelles machines ---------------------------------------------


def pages_embed(site_url: str) -> dict[str, Any]:
    return embed(
        "Classement redéployé", link(escape_md(site_url), site_url), url=site_url, color=GREEN
    )


def new_machine_embeds(summary: dict[str, Any], site_url: str) -> list[dict[str, Any]]:
    ranked = int(summary.get("ranked") or 0)
    embeds = []
    for machine in summary.get("machines", []):
        slug = str(machine.get("slug", ""))
        page = f"{site_url.rstrip('/')}/machines/{quote(slug)}.html" if site_url else None
        if machine.get("rank") is None:
            score = "non classé (score combiné sans les trois catégories)"
            rank = "—"
        else:
            score = f"{fr_int(round(float(machine['combined'])))} points"
            rank = f"{int(machine['rank'])} / {ranked}"
        embeds.append(
            embed(
                f"Nouvelle machine : {truncate(str(machine.get('machine') or slug), 200)}",
                url=page,
                color=BLUE,
                fields=[field("Score combiné", score, True), field("Rang", rank, True)],
            )
        )
    return embeds


# --- veille.yml --------------------------------------------------------------------------------

# backend hwbench -> paquet Arch Linux (archlinux.org/packages/search/json)
ARCH_PACKAGES = {"sysbench": "sysbench", "glmark2": "glmark2", "vkmark": "vkmark"}


def reference_tool_versions(reference: dict[str, Any]) -> dict[str, str]:
    return {
        b["backend"]: b["tool_version"]
        for b in reference.get("benchmarks", [])
        if b.get("backend") in ARCH_PACKAGES and b.get("tool_version")
    }


def arch_version(search: dict[str, Any], package: str) -> str | None:
    """pkgver (sans epoch ni pkgrel) du paquet exact dans une réponse de recherche Arch."""
    for result in search.get("results", []):
        if result.get("pkgname") == package and result.get("pkgver"):
            return str(result["pkgver"])
    return None


def ci_python_versions(ci_yaml: str) -> list[str]:
    """Versions de la matrice python-version de ci.yml (liste en ligne, seule forme utilisée)."""
    match = re.search(r"python-version:\s*\[([^\]]*)\]", ci_yaml)
    return re.findall(r"\d+\.\d+", match.group(1)) if match else []


def _minor(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def new_python_releases(
    releases: list[dict[str, Any]], matrix: list[str], today: date
) -> list[str]:
    """Versions mineures stables sorties (releaseDate passée), plus récentes que la matrice."""
    if not matrix:
        return []
    newest = max(_minor(v) for v in matrix)
    found = []
    for release in releases:
        name = str(release.get("name", ""))
        if not re.fullmatch(r"\d+\.\d+", name) or _minor(name) <= newest:
            continue
        try:
            released = date.fromisoformat(str(release.get("releaseDate")))
        except ValueError:
            continue
        if released <= today:
            found.append(name)
    return sorted(found, key=_minor)


def veille_embed(
    reference: dict[str, str], arch: dict[str, str | None], new_pythons: list[str]
) -> dict[str, Any] | None:
    lines = [
        f"• **{backend}** : {escape_md(arch[backend])} sur Arch Linux, "
        f"référence mesurée avec {escape_md(version)}"
        for backend, version in sorted(reference.items())
        if arch.get(backend) and arch[backend] != version
    ]
    fields = []
    if lines:
        fields.append(
            field(
                "Outils de bench",
                "\n".join(lines) + "\nNouvelle version d'outil = nouvelle identité de backend : "
                "régénérer la référence sur le desktop B850 quand elle y est installée.",
            )
        )
    if new_pythons:
        fields.append(
            field(
                "Python",
                f"{', '.join(new_pythons)} disponible, absent de la matrice de "
                "`.github/workflows/ci.yml`.",
            )
        )
    if not fields:
        return None
    return embed("Veille : nouvelles versions", color=AMBER, fields=fields)


# --- hebdo.yml ---------------------------------------------------------------------------------


def hebdo_embed(stats: dict[str, Any]) -> dict[str, Any]:
    def number(key: str) -> str:
        value = stats.get(key)
        return fr_int(int(value)) if value is not None else "non disponible"

    ci_lines = []
    for branch, run in (stats.get("ci") or {}).items():
        if run is None:
            ci_lines.append(f"• {branch} : non disponible")
        else:
            label = "réussie" if run.get("conclusion") == "success" else "en échec"
            if run.get("conclusion") not in FAILED | {"success"}:
                label = escape_md(run.get("conclusion") or "inconnue")
            when = fr_date(run.get("created_at"))
            ci_lines.append(f"• {branch} : {link(label, run.get('html_url'))} ({when})")
    release = stats.get("release")
    release_text = (
        f"{link(escape_md(release.get('tag_name', '?')), release.get('html_url'))} "
        f"({fr_date(release.get('published_at'))})"
        if release
        else "non disponible"
    )
    return embed(
        "Rapport hebdomadaire",
        color=BLUE,
        fields=[
            field("Téléchargements PyPI (7 jours)", number("downloads_week"), True),
            field("Étoiles", number("stars"), True),
            field("Machines au classement", number("machines"), True),
            field("PR ouvertes", number("open_prs"), True),
            field("Issues ouvertes", number("open_issues"), True),
            field("Dernière release", release_text, True),
            field("Dernière CI", "\n".join(ci_lines) or "non disponible"),
        ],
    )


def _safely(source: str, function: Callable[[], Any]) -> Any:
    """Une source injoignable devient « non disponible » au lieu d'annuler tout le rapport."""
    try:
        return function()
    except Exception as exc:  # noqa: BLE001 — toute erreur réseau ou de format
        warn(f"{source} : {type(exc).__name__}")
        return None


def hebdo_stats(repo: str, results_dir: Path, api: Api, fetch: Api) -> dict[str, Any]:
    def latest_ci(branch: str) -> dict[str, Any] | None:
        runs = api(
            f"/repos/{repo}/actions/workflows/ci.yml/runs"
            f"?branch={branch}&event=push&status=completed&per_page=1"
        ).get("workflow_runs", [])
        return runs[0] if runs else None

    def count(kind: str) -> int:
        return api(f"/search/issues?q=repo:{repo}+is:{kind}+is:open&per_page=1")["total_count"]

    pypi_url = f"https://pypistats.org/api/packages/{PACKAGE}/recent"
    return {
        "downloads_week": _safely("pypistats", lambda: fetch(pypi_url)["data"]["last_week"]),
        "stars": _safely("dépôt", lambda: api(f"/repos/{repo}")["stargazers_count"]),
        "open_prs": _safely("PR ouvertes", lambda: count("pr")),
        "open_issues": _safely("issues ouvertes", lambda: count("issue")),
        "ci": {b: _safely(f"CI {b}", lambda b=b: latest_ci(b)) for b in WATCHED_BRANCHES[::-1]},
        "machines": _safely("results/", lambda: len(list(results_dir.glob("*.json")))),
        "release": _safely("release", lambda: api(f"/repos/{repo}/releases/latest")),
    }


# --- Commandes ---------------------------------------------------------------------------------


def _repo() -> str:
    return os.environ["GITHUB_REPOSITORY"]


def build(args: argparse.Namespace) -> tuple[str, list[dict[str, Any]]]:
    """(variable du webhook, embeds) de la commande. Peut lever : main() en fait un warning."""
    command = args.command
    if command == "ci":
        return "DISCORD_WEBHOOK_CI", ci_messages(read_event(), github_api)
    if command == "results":
        return "DISCORD_WEBHOOK_CLASSEMENT", results_messages(read_event(), github_api)
    if command == "dependabot":
        return "DISCORD_WEBHOOK_DEPENDABOT", dependabot_messages(read_event(), github_api)
    if command == "release":
        release = github_api(f"/repos/{_repo()}/releases/tags/{quote(args.tag, safe='')}")
        return "DISCORD_WEBHOOK_RELEASES", [release_embed(release, _repo())]
    if command == "pypi-pending":
        return "DISCORD_WEBHOOK_DEPLOIEMENTS", [pypi_pending_embed(args.version, args.run_url)]
    if command == "pypi-published":
        return "DISCORD_WEBHOOK_DEPLOIEMENTS", [pypi_published_embed(args.version)]
    if command == "pages":
        return "DISCORD_WEBHOOK_DEPLOIEMENTS", [pages_embed(args.url)]
    if command == "new-machines":
        summary = json.loads(os.environ.get("SUMMARY") or "{}")
        return "DISCORD_WEBHOOK_CLASSEMENT", new_machine_embeds(summary, args.site_url)
    if command == "veille":
        reference = reference_tool_versions(json.loads(args.reference.read_text("utf-8")))
        arch = {
            backend: _safely(
                f"Arch Linux ({package})",
                lambda p=package: arch_version(
                    fetch_json(f"https://archlinux.org/packages/search/json/?name={p}"), p
                ),
            )
            for backend, package in ARCH_PACKAGES.items()
        }
        releases = _safely(
            "endoflife.date",
            lambda: fetch_json("https://endoflife.date/api/v1/products/python")["result"][
                "releases"
            ],
        )
        for backend in sorted(set(reference) - {b for b, v in arch.items() if v}):
            warn(f"version Arch Linux de {backend} introuvable")
        matrix = ci_python_versions(args.ci_workflow.read_text("utf-8"))
        today = datetime.now(UTC).date()
        found = veille_embed(reference, arch, new_python_releases(releases or [], matrix, today))
        print(
            f"référence {reference}, Arch {arch}, matrice Python {matrix} : "
            f"{'message envoyé' if found else 'rien à signaler'}"
        )
        return "DISCORD_WEBHOOK_VEILLE", [found] if found else []
    if command == "hebdo":
        stats = hebdo_stats(_repo(), args.results, github_api, fetch_json)
        return "DISCORD_WEBHOOK_HEBDO", [hebdo_embed(stats)]
    raise ValueError(f"commande inconnue : {command}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("ci", help="workflow_run : échec ou retour au vert sur dev/main -> #ci")
    sub.add_parser("results", help="workflow_run Results : soumission -> #classement")
    sub.add_parser("dependabot", help="workflow_run CI d'une PR Dependabot -> #dependabot")
    release = sub.add_parser("release", help="GitHub Release créée -> #releases")
    release.add_argument("--tag", required=True)
    pending = sub.add_parser("pypi-pending", help="PyPI en attente -> #deploiements")
    pending.add_argument("--version", required=True)
    pending.add_argument("--run-url", required=True)
    published = sub.add_parser("pypi-published", help="publié sur PyPI -> #deploiements")
    published.add_argument("--version", required=True)
    pages = sub.add_parser("pages", help="site déployé -> #deploiements")
    pages.add_argument("--url", required=True)
    machines = sub.add_parser("new-machines", help="résumé JSON dans $SUMMARY -> #classement")
    machines.add_argument("--site-url", default="")
    veille = sub.add_parser("veille", help="versions des outils et de Python -> #veille")
    veille.add_argument("--reference", type=Path, required=True)
    veille.add_argument("--ci-workflow", type=Path, required=True)
    hebdo = sub.add_parser("hebdo", help="rapport hebdomadaire -> #rapport-hebdo")
    hebdo.add_argument("--results", type=Path, default=Path("results"))
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        webhook_env, embeds = build(args)
    except Exception as exc:  # noqa: BLE001 — une notification ne fait jamais échouer un job
        warn(f"notification « {args.command} » non construite : {type(exc).__name__}: {exc}")
        return 0
    if not embeds:
        print(f"{args.command} : rien à notifier")
        return 0
    deliver(webhook_env, payloads(embeds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
