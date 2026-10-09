"""scripts/discord_notify.py : construction des messages (pur), envoi simulé, aucun réseau."""

import importlib.util
import io
import json
import sys
from datetime import date
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "discord_notify.py"
_spec = importlib.util.spec_from_file_location("discord_notify", SCRIPT)
dn = importlib.util.module_from_spec(_spec)
sys.modules["discord_notify"] = dn
_spec.loader.exec_module(dn)

WEBHOOK = "https://discord.com/api/webhooks/123456/SECRET-TOKEN-xyz"
REPO = "Mvth1s/hwbench"


def all_text(payload) -> str:
    return json.dumps(payload, ensure_ascii=False)


def http_error(code: int, body: bytes = b"", headers: dict | None = None) -> HTTPError:
    msg = Message()
    for key, value in (headers or {}).items():
        msg[key] = value
    # le texte de l'exception cite l'URL : il ne doit jamais être affiché
    return HTTPError(WEBHOOK, code, f"erreur {WEBHOOK}", msg, io.BytesIO(body))


class FakeOpener:
    """Réponses successives : une exception est levée, sinon un succès (204)."""

    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if isinstance(outcome, Exception):
            raise outcome
        return io.BytesIO(b"")


# --- texte et limites --------------------------------------------------------------------------


def test_truncate() -> None:
    assert dn.truncate("abc", 3) == "abc"
    assert dn.truncate("abcdef", 4) == "abc…"
    assert len(dn.truncate("x" * 5000, dn.DESCRIPTION_MAX)) == dn.DESCRIPTION_MAX


def test_escape_md_neutralises_links_mentions_and_formatting() -> None:
    evil = "[clic](https://evil.example) @everyone <@123> **gras** `code` # titre"
    escaped = dn.escape_md(evil)
    assert "[clic](" not in escaped and "\\[clic\\]\\(" in escaped
    assert "\\@everyone" in escaped and "\\<\\@123\\>" in escaped
    assert "**" not in escaped.replace("\\*", "")


def test_embed_respects_every_discord_limit() -> None:
    fields = [dn.field("n" * 400, "v" * 2000) for _ in range(40)]
    e = dn.embed("t" * 400, "d" * 9000, fields=fields, footer="f" * 3000)
    assert len(e["title"]) <= dn.TITLE_MAX
    assert len(e["description"]) <= dn.DESCRIPTION_MAX
    assert len(e["fields"]) <= dn.FIELDS_MAX
    assert all(len(f["name"]) <= dn.FIELD_NAME_MAX for f in e["fields"])
    assert all(len(f["value"]) <= dn.FIELD_VALUE_MAX for f in e["fields"])
    assert len(e["footer"]["text"]) <= dn.FOOTER_MAX
    assert dn._embed_size(e) <= dn.EMBED_TOTAL_MAX


def test_embed_drops_non_https_urls() -> None:
    assert "url" not in dn.embed("t", url="javascript:alert(1)")
    assert dn.link("x", "javascript:alert(1)") == "x"
    assert dn.link("x", "https://a.example") == "[x](https://a.example)"


def test_payloads_split_and_never_mention() -> None:
    embeds = [dn.embed(f"m{i}", "d" * 1000) for i in range(25)]
    messages = dn.payloads(embeds)
    assert sum(len(m["embeds"]) for m in messages) == 25
    for m in messages:
        assert m["allowed_mentions"] == {"parse": []}
        assert len(m["embeds"]) <= dn.EMBEDS_PER_MESSAGE
        assert sum(dn._embed_size(e) for e in m["embeds"]) <= dn.EMBED_TOTAL_MAX


# --- envoi -------------------------------------------------------------------------------------


def test_send_posts_json_with_a_user_agent() -> None:
    opener = FakeOpener()
    assert dn.send(WEBHOOK, {"embeds": []}, opener=opener)
    request = opener.requests[0]
    assert request.get_method() == "POST"
    assert request.get_header("User-agent") == dn.USER_AGENT
    assert json.loads(request.data) == {"embeds": []}


def test_send_waits_retry_after_on_429() -> None:
    slept = []
    opener = FakeOpener(http_error(429, b'{"retry_after": 2.5}'), None)
    assert dn.send(WEBHOOK, {}, opener=opener, sleep=slept.append)
    assert slept == [2.5] and len(opener.requests) == 2


def test_retry_after_header_fallback_and_cap() -> None:
    assert dn._retry_after(http_error(429, b"", {"Retry-After": "3"})) == 3.0
    assert dn._retry_after(http_error(429, b'{"retry_after": 9999}')) == dn.RETRY_AFTER_MAX
    assert dn._retry_after(http_error(429, b"pas du json")) == 1.0


def test_send_gives_up_after_repeated_429(capsys) -> None:
    opener = FakeOpener(*[http_error(429, b'{"retry_after": 0}') for _ in range(4)])
    assert not dn.send(WEBHOOK, {}, opener=opener, sleep=lambda _: None)
    assert len(opener.requests) == 4
    out = capsys.readouterr().out
    assert "::warning" in out and "HTTP 429" in out


@pytest.mark.parametrize(
    "error",
    [http_error(404), http_error(500), URLError(f"no route {WEBHOOK}"), TimeoutError(WEBHOOK)],
)
def test_send_failures_warn_without_the_url(error, capsys) -> None:
    assert not dn.send(WEBHOOK, {}, opener=FakeOpener(error), sleep=lambda _: None)
    out = capsys.readouterr().out
    assert "::warning" in out
    assert WEBHOOK not in out and "SECRET-TOKEN" not in out and "123456" not in out


def test_missing_secret_is_a_warning(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DISCORD_WEBHOOK_CI", raising=False)
    opener = FakeOpener()
    dn.deliver("DISCORD_WEBHOOK_CI", [{"embeds": []}], opener=opener)
    assert opener.requests == []
    assert "secret DISCORD_WEBHOOK_CI absent" in capsys.readouterr().out


def test_main_never_fails_and_never_prints_the_url(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_CI", WEBHOOK)
    # événement illisible : avertissement, code 0
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "absent.json"))
    assert dn.main(["ci"]) == 0
    out = capsys.readouterr().out
    assert "::warning" in out and WEBHOOK not in out


def test_warning_stays_on_one_line(capsys) -> None:
    dn.warn("a\n::error::b")
    assert capsys.readouterr().out.count("\n") == 1


# --- #ci ---------------------------------------------------------------------------------------


def run(**overrides):
    base = {
        "id": 10,
        "name": "CI",
        "event": "push",
        "head_branch": "dev",
        "head_sha": "abcdef1234567890",
        "head_repository": {"full_name": REPO, "owner": {"login": "Mvth1s"}},
        "head_commit": {"message": "fix: something [x](https://evil.example)\n\nbody"},
        "html_url": "https://github.com/Mvth1s/hwbench/actions/runs/10",
        "conclusion": "failure",
        "workflow_id": 7,
        "run_attempt": 1,
        "created_at": "2026-10-09T10:00:00Z",
        "pull_requests": [],
        "actor": {"login": "Mvth1s"},
        "display_title": "titre",
    }
    return base | overrides


def event(**overrides):
    return {"workflow_run": run(**overrides), "repository": {"full_name": REPO}}


class FakeApi:
    def __init__(self, routes: dict) -> None:
        self.routes = routes
        self.calls = []

    def __call__(self, path: str):
        self.calls.append(path)
        for prefix, value in self.routes.items():
            if path.startswith(prefix):
                return value
        raise AssertionError(f"appel inattendu : {path}")


JOBS = {
    "jobs": [
        {"id": 1, "name": "lint", "conclusion": "success", "html_url": "https://g/1"},
        {"id": 2, "name": "test (3.11)", "conclusion": "failure", "html_url": "https://g/2"},
    ]
}


def test_ci_failure_lists_failed_jobs() -> None:
    api = FakeApi({f"/repos/{REPO}/actions/runs/10/jobs": JOBS})
    [e] = dn.ci_messages(event(), api)
    assert e["title"] == "CI en échec sur dev" and e["color"] == dn.RED
    jobs = e["fields"][0]["value"]
    assert "test \\(3.11\\)" in jobs and "lint" not in jobs
    assert "`abcdef1`" in e["description"] and "[x](" not in e["description"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"event": "pull_request"},
        {"head_branch": "feature"},
        {"head_repository": {"full_name": "fork/hwbench"}},
        {"conclusion": "cancelled"},
    ],
)
def test_ci_ignores_other_runs(overrides) -> None:
    assert dn.ci_messages(event(**overrides), FakeApi({})) == []


def previous_runs(*conclusions):
    return {
        "workflow_runs": [
            {"id": 10 + i, "conclusion": c, "created_at": f"2026-10-0{9 - i}T09:00:00Z"}
            for i, c in enumerate(conclusions, 1)
        ]
    }


def test_back_to_green_after_a_failure() -> None:
    api = FakeApi({f"/repos/{REPO}/actions/workflows/7/runs": previous_runs("failure")})
    [e] = dn.ci_messages(event(conclusion="success"), api)
    assert e["title"] == "CI de nouveau au vert sur dev" and e["color"] == dn.GREEN
    assert "branch=dev&event=push&status=completed" in api.calls[0]


def test_no_message_when_already_green() -> None:
    api = FakeApi({f"/repos/{REPO}/actions/workflows/7/runs": previous_runs("success")})
    assert dn.ci_messages(event(conclusion="success"), api) == []


def test_previous_conclusion_skips_cancelled_and_later_runs() -> None:
    current = run(created_at="2026-10-09T10:00:00Z")
    runs = [
        {"id": 1, "conclusion": "failure", "created_at": "2026-10-08T10:00:00Z"},
        {"id": 2, "conclusion": "cancelled", "created_at": "2026-10-09T09:00:00Z"},
        {"id": 3, "conclusion": "success", "created_at": "2026-10-09T11:00:00Z"},
        {"id": 10, "conclusion": "success", "created_at": "2026-10-09T10:00:00Z"},
    ]
    assert dn.previous_conclusion(runs, current) == "failure"
    assert dn.previous_conclusion([], current) is None


def test_rerun_compares_with_the_previous_attempt() -> None:
    api = FakeApi({f"/repos/{REPO}/actions/runs/10/attempts/1": {"conclusion": "failure"}})
    assert len(dn.ci_messages(event(conclusion="success", run_attempt=2), api)) == 1


# --- #classement (Results) ---------------------------------------------------------------------

PR = {
    "number": 42,
    "title": "Ajout [machine](https://evil.example) @everyone",
    "html_url": "https://github.com/Mvth1s/hwbench/pull/42",
    "user": {"login": "contrib"},
    "head": {"sha": "abcdef1234567890"},
}


def results_event(**overrides):
    return event(name="Results", event="pull_request", head_branch="add-machine", **overrides)


def test_results_accepted_with_pr_from_the_run() -> None:
    api = FakeApi({f"/repos/{REPO}/pulls/42": PR})
    [e] = dn.results_messages(
        results_event(conclusion="success", pull_requests=[{"number": 42}]), api
    )
    assert e["title"] == "Soumission au classement validée"
    assert e["url"] == PR["html_url"]
    assert "\\#42" in e["description"] and "[machine](" not in e["description"]
    assert "@everyone" not in e["description"].replace("\\@", "")


def test_results_refused_from_a_fork_lists_annotations() -> None:
    fork = {"full_name": "contrib/hwbench", "owner": {"login": "contrib"}}
    api = FakeApi(
        {
            f"/repos/{REPO}/actions/runs/10/jobs": {
                "jobs": [{"id": 99, "conclusion": "failure", "steps": []}]
            },
            f"/repos/{REPO}/check-runs/99/annotations": [
                {"annotation_level": "failure", "message": "results/x.json : schéma inconnu"},
                {"annotation_level": "failure", "message": "Process completed with exit code 1."},
                {"annotation_level": "warning", "message": "bruit"},
            ],
            f"/repos/{REPO}/pulls?state=all&head=contrib%3Aadd-machine": [
                {"number": 7, "head": {"sha": "autre"}},
                PR,
            ],
        }
    )
    [e] = dn.results_messages(results_event(head_repository=fork), api)
    assert e["title"] == "Soumission au classement refusée" and e["color"] == dn.RED
    reasons = next(f["value"] for f in e["fields"] if f["name"] == "Raisons")
    assert "schéma inconnu" in reasons
    assert "exit code" not in reasons and "bruit" not in reasons
    assert "\\#42" in e["description"]


def test_refusal_falls_back_to_failed_steps() -> None:
    api = FakeApi(
        {
            f"/repos/{REPO}/actions/runs/10/jobs": {
                "jobs": [
                    {
                        "id": 5,
                        "conclusion": "failure",
                        "steps": [
                            {
                                "name": "results/ doit rester un vrai dossier",
                                "conclusion": "failure",
                            }
                        ],
                    }
                ]
            },
            f"/repos/{REPO}/check-runs/5/annotations": [],
        }
    )
    assert dn.refusal_reasons(results_event(), api) == [
        "étape en échec : results/ doit rester un vrai dossier"
    ]


def test_results_ignores_cancelled_runs() -> None:
    assert dn.results_messages(results_event(conclusion="cancelled"), FakeApi({})) == []


# --- #dependabot -------------------------------------------------------------------------------


def test_dependabot_ci_result() -> None:
    pr = PR | {"title": "ci(deps): bump actions/checkout from 6 to 7"}
    api = FakeApi({f"/repos/{REPO}/pulls/3": pr})
    ev = event(
        event="pull_request",
        conclusion="success",
        actor={"login": "dependabot[bot]"},
        pull_requests=[{"number": 3}],
    )
    [e] = dn.dependabot_messages(ev, api)
    assert e["title"] == "PR Dependabot : CI réussie" and e["color"] == dn.GREEN
    assert "bump actions/checkout" in e["description"]


def test_dependabot_ignores_other_actors() -> None:
    assert dn.dependabot_messages(event(event="pull_request"), FakeApi({})) == []


# --- release.yml, pages.yml --------------------------------------------------------------------

RELEASE_BODY = """## v0.5.0 (2026-10-10)

### Features

- **leaderboard**: Add a summary command ([`a9c8ead`](https://github.com/Mvth1s/hwbench/commit/a9c8ead))

### Bug Fixes

- **display**: Never raise ([`dc3c28a`](https://github.com/Mvth1s/hwbench/commit/dc3c28a))
"""


def test_changelog_excerpt_drops_heading_and_commit_links() -> None:
    text = dn.changelog_excerpt(RELEASE_BODY)
    assert not text.startswith("## v0.5.0")
    assert "**Features**" in text and "Add a summary command" in text
    assert "a9c8ead" not in text


def test_changelog_excerpt_cuts_on_a_line() -> None:
    body = "\n".join(f"- ligne {i}" for i in range(500))
    text = dn.changelog_excerpt(body, limit=200)
    assert len(text) <= 200 and text.endswith("\n…")
    assert all(line.startswith("- ligne") for line in text.splitlines()[:-1])


def test_release_embed() -> None:
    release = {"tag_name": "v0.5.0", "body": RELEASE_BODY, "html_url": "https://g/r"}
    e = dn.release_embed(release, REPO)
    assert e["title"] == "hwbench 0.5.0 publiée"
    values = " ".join(f["value"] for f in e["fields"])
    assert "https://pypi.org/project/hwbench/0.5.0/" in values
    assert "pip download hwbench==0.5.0 --no-deps" in values
    assert f"gh attestation verify hwbench-0.5.0-py3-none-any.whl --repo {REPO}" in values


def test_pypi_and_pages_embeds() -> None:
    pending = dn.pypi_pending_embed("0.5.0", "https://github.com/x/actions/runs/1")
    assert "attente" in pending["title"] and pending["url"].endswith("/runs/1")
    assert dn.pypi_published_embed("0.5.0")["url"] == "https://pypi.org/project/hwbench/0.5.0/"
    assert dn.pages_embed("https://mvth1s.github.io/hwbench/")["color"] == dn.GREEN


def test_new_machines() -> None:
    summary = {
        "ranked": 4,
        "machines": [
            {"slug": "rapide", "machine": "Desktop @everyone", "combined": 2345.6, "rank": 1},
            {"slug": "portable", "machine": "Portable", "combined": None, "rank": None},
        ],
    }
    first, second = dn.new_machine_embeds(summary, "https://mvth1s.github.io/hwbench/")
    assert first["url"] == "https://mvth1s.github.io/hwbench/machines/rapide.html"
    values = {f["name"]: f["value"] for f in first["fields"]}
    assert values == {"Score combiné": "2 346 points", "Rang": "1 / 4"}
    assert "non classé" in second["fields"][0]["value"]
    assert all_text(dn.payloads([first, second])).count('"parse": []') == 1


def test_new_machines_from_env(monkeypatch) -> None:
    monkeypatch.setenv("SUMMARY", json.dumps({"ranked": 1, "machines": []}))
    args = dn.parser().parse_args(["new-machines", "--site-url", "https://x.example/"])
    assert dn.build(args) == ("DISCORD_WEBHOOK_CLASSEMENT", [])


# --- veille ------------------------------------------------------------------------------------


def test_reference_tool_versions_from_the_real_reference() -> None:
    reference = json.loads(
        (SCRIPT.parents[1] / "src/hwbench/data/reference.json").read_text("utf-8")
    )
    versions = dn.reference_tool_versions(reference)
    assert set(versions) == {"sysbench", "glmark2", "vkmark"}


def test_arch_version_takes_the_exact_package() -> None:
    search = {
        "results": [
            {"pkgname": "glmark2-git", "pkgver": "9999"},
            {"pkgname": "glmark2", "pkgver": "2023.01", "pkgrel": "2", "epoch": 1},
        ]
    }
    assert dn.arch_version(search, "glmark2") == "2023.01"
    assert dn.arch_version({"results": []}, "glmark2") is None


def test_ci_python_versions_from_the_real_workflow() -> None:
    ci = (SCRIPT.parents[1] / ".github/workflows/ci.yml").read_text("utf-8")
    assert dn.ci_python_versions(ci) == ["3.11", "3.12", "3.13", "3.14"]


def test_new_python_releases() -> None:
    releases = [
        {"name": "3.16", "releaseDate": "2027-10-01"},
        {"name": "3.15", "releaseDate": "2026-10-01"},
        {"name": "3.14", "releaseDate": "2025-10-07"},
        {"name": "2.7", "releaseDate": "2010-07-03"},
    ]
    matrix = ["3.11", "3.14"]
    assert dn.new_python_releases(releases, matrix, date(2026, 10, 9)) == ["3.15"]
    assert dn.new_python_releases(releases, matrix, date(2026, 9, 30)) == []


def test_veille_embed() -> None:
    reference = {"glmark2": "2023.01", "vkmark": "2025.01", "sysbench": "1.0.20"}
    same = {"glmark2": "2023.01", "vkmark": "2025.01", "sysbench": "1.0.20"}
    assert dn.veille_embed(reference, same, []) is None
    # source injoignable (None) : pas une différence
    assert dn.veille_embed(reference, same | {"vkmark": None}, []) is None
    e = dn.veille_embed(reference, same | {"vkmark": "2026.01"}, ["3.15"])
    text = all_text(e)
    assert "vkmark" in text and "2026.01" in text and "2025.01" in text
    assert "glmark2" not in text and "3.15" in text


# --- hebdo -------------------------------------------------------------------------------------


def test_hebdo_stats_survive_a_failing_source(tmp_path, capsys) -> None:
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "b.json").write_text("{}")

    def fetch(url):
        raise URLError("pypistats en panne")

    api = FakeApi(
        {
            f"/repos/{REPO}/actions/workflows/ci.yml/runs": {
                "workflow_runs": [{"conclusion": "success", "html_url": "https://g/ci"}]
            },
            "/search/issues?q=repo:Mvth1s/hwbench+is:pr": {"total_count": 2},
            "/search/issues?q=repo:Mvth1s/hwbench+is:issue": {"total_count": 0},
            f"/repos/{REPO}/releases/latest": {"tag_name": "v0.4.0"},
            f"/repos/{REPO}": {"stargazers_count": 1234},
        }
    )
    stats = dn.hebdo_stats(REPO, tmp_path, api, fetch)
    assert stats["downloads_week"] is None
    assert stats["machines"] == 2 and stats["open_prs"] == 2 and stats["open_issues"] == 0
    assert list(stats["ci"]) == ["main", "dev"]
    assert "pypistats" in capsys.readouterr().out

    values = {f["name"]: f["value"] for f in dn.hebdo_embed(stats)["fields"]}
    assert values["Téléchargements PyPI (7 jours)"] == "non disponible"
    assert values["Étoiles"] == "1 234"
    assert values["Issues ouvertes"] == "0"
    assert "main : [réussie](https://g/ci)" in values["Dernière CI"]
