"""Règles d'écriture des workflows (.github/workflows/) et structure du pipeline ci.yml."""

import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
FILES = sorted(WORKFLOWS.glob("*.yml"))

# jobs vérifiés sur chaque PR, agrégés par ci-ok (seul check requis)
CHECKS = {"changes", "lint", "typecheck", "test", "build", "audit", "commitlint"}
# jobs coûteux sautés quand seule la documentation change
COSTLY = {"lint", "typecheck", "test", "build", "audit"}


def load(path: Path) -> dict:
    workflow = yaml.safe_load(path.read_text("utf-8"))
    # YAML 1.1 : la clé « on » est lue comme le booléen True
    workflow["on"] = workflow.pop(True, workflow.get("on"))
    return workflow


@pytest.fixture(scope="module")
def ci() -> dict:
    return load(WORKFLOWS / "ci.yml")


def needs(job: dict) -> set[str]:
    value = job.get("needs", [])
    return {value} if isinstance(value, str) else set(value)


def ancestors(jobs: dict, name: str) -> set[str]:
    found: set[str] = set()
    todo = list(needs(jobs[name]))
    while todo:
        job = todo.pop()
        if job not in found:
            found.add(job)
            todo += needs(jobs[job])
    return found


def test_the_old_workflows_are_gone() -> None:
    names = {path.name for path in FILES}
    assert not names & {"commitlint.yml", "release.yml", "pages.yml"}
    assert {"ci.yml", "codeql.yml", "audit.yml"} <= names


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_every_action_is_pinned_by_commit_sha_with_its_exact_tag(path: Path) -> None:
    for line in path.read_text("utf-8").splitlines():
        if match := re.match(r"\s*(?:-\s+)?uses:\s*(\S+)(.*)$", line):
            action, rest = match.groups()
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", action), line
            assert re.fullmatch(r"\s+# v\d+\.\d+\.\d+", rest), line


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_read_only_by_default_and_a_timeout_on_every_job(path: Path) -> None:
    workflow = load(path)
    assert workflow["permissions"] in ({}, {"contents": "read"})
    for name, job in workflow["jobs"].items():
        assert isinstance(job.get("timeout-minutes"), int), f"{path.name}:{name}"


def test_id_token_only_where_it_is_needed() -> None:
    jobs = {
        f"{path.name}:{name}"
        for path in FILES
        for name, job in load(path)["jobs"].items()
        if (job.get("permissions") or {}).get("id-token") == "write"
    }
    # attestation de provenance, trusted publishing PyPI, déploiement Pages
    assert jobs == {"ci.yml:release", "ci.yml:pypi", "ci.yml:deploy"}


# produisent le dist publié (PyPI, GitHub Release) ou le site déployé : aucun cache restauré
PUBLISHING = {"ci.yml:build", "ci.yml:site-prod", "ci.yml:site-preview"}


def test_pip_is_cached_except_where_a_published_artifact_is_built() -> None:
    seen = set()
    for path in FILES:
        for name, job in load(path)["jobs"].items():
            for step in job.get("steps", []):
                if "actions/setup-python@" in step.get("uses", ""):
                    key = f"{path.name}:{name}"
                    seen.add(key)
                    expected = None if key in PUBLISHING else "pip"
                    assert step["with"].get("cache") == expected, key
    assert seen >= PUBLISHING


def test_no_path_filter_can_leave_ci_ok_pending(ci: dict) -> None:
    for event in ci["on"].values():
        assert not {"paths", "paths-ignore"} & set(event or {})
    assert ci["on"]["pull_request"] is None  # toutes les bases


def test_ci_ok_aggregates_every_check(ci: dict) -> None:
    jobs = ci["jobs"]
    assert needs(jobs["ci-ok"]) == CHECKS
    assert jobs["ci-ok"]["if"] == "always()"
    step = jobs["ci-ok"]["steps"][0]["env"]["FAILED"]
    assert "'failure'" in step and "'cancelled'" in step
    # tout job lancé sur une PR, hors du contrôle de liens non bloquant, est dans ci-ok
    on_pr = {
        name
        for name, job in jobs.items()
        if "github.event_name == 'push'" not in str(job.get("if", ""))
        and "refs/heads/main" not in str(job.get("if", ""))
        and not ancestors(jobs, name) & {"release", "site-prod", "site-preview"}
    }
    assert on_pr - {"ci-ok", "links"} == CHECKS
    assert jobs["links"]["continue-on-error"] is True


def test_costly_jobs_are_skipped_for_documentation_only(ci: dict) -> None:
    jobs = ci["jobs"]
    for name in COSTLY:
        assert "changes" in needs(jobs[name])
        assert jobs[name]["if"] == "needs.changes.outputs.code == 'true'"
    assert "changes" not in needs(jobs["commitlint"])
    assert "if" in jobs["commitlint"] and "code" not in jobs["commitlint"]["if"]


def test_chain_lint_typecheck_test_build(ci: dict) -> None:
    jobs = ci["jobs"]
    assert "lint" in needs(jobs["typecheck"])
    assert "typecheck" in needs(jobs["test"])
    assert "test" in needs(jobs["build"])


def test_cancel_in_progress_only_on_pull_requests(ci: dict) -> None:
    assert ci["concurrency"]["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"
    deploy = ci["jobs"]["deploy"]["concurrency"]
    assert deploy == {"group": "pages", "cancel-in-progress": False}


def test_release_publishes_the_tested_build(ci: dict) -> None:
    jobs = ci["jobs"]
    assert {"build", "ci-ok"} <= needs(jobs["release"])
    assert "refs/heads/main" in jobs["release"]["if"]
    assert needs(jobs["pypi"]) == {"release"}
    assert jobs["pypi"]["environment"]["name"] == "pypi"
    assert jobs["pypi"]["permissions"] == {"id-token": "write"}
    for name in ("release", "pypi"):
        downloads = [s for s in jobs[name]["steps"] if "download-artifact@" in s.get("uses", "")]
        assert [s["with"]["name"] for s in downloads] == ["dist"]
    psr = [s for s in jobs["release"]["steps"] if "python-semantic-release@" in s.get("uses", "")]
    assert psr[0]["with"]["build"] == "false"
    upload = next(s for s in jobs["build"]["steps"] if "upload-artifact@" in s.get("uses", ""))
    assert upload["with"]["retention-days"] == 14


def test_results_on_main_redeploy_the_production_site(ci: dict) -> None:
    """Une mise à jour de results/ sur main (PR de soumission fusionnée) redéploie la prod.

    results/ n'est pas de la documentation (tests/test_ci_changes.py), donc build tourne ; la
    génération du site ne dépend que de build et ci-ok, et tolère une release sautée (aucune
    version à publier). pages.yml n'existe plus : c'est le seul chemin vers la prod.
    """
    jobs = ci["jobs"]
    assert "main" in ci["on"]["push"]["branches"]
    assert {"site", "site-prod", "build"} <= ancestors(jobs, "deploy")
    for name in ("site-prod", "site-preview"):
        condition = " ".join(jobs[name]["if"].split())
        assert condition.startswith("always() && github.event_name == 'push'")
        assert "needs.build.result == 'success'" in condition
        assert "needs.ci-ok.result == 'success'" in condition
        assert "changes" not in condition
        for skippable in ("release", "pypi"):
            assert (
                f'contains(fromJSON(\'["success", "skipped"]\'), needs.{skippable}.result)'
                in condition
            )
    assert jobs["deploy"]["environment"]["name"] == "github-pages"


def test_preview_is_built_apart_from_production(ci: dict) -> None:
    jobs = ci["jobs"]
    run = " ".join(s.get("run", "") for s in jobs["site-preview"]["steps"])
    assert "--preview" in run
    assert "--preview" not in " ".join(s.get("run", "") for s in jobs["site-prod"]["steps"])
    # l'assemblage n'exécute aucun code du dépôt
    assembly = jobs["site"]["steps"]
    assert all("run" not in step for step in assembly)
    assert [s["with"]["path"] for s in assembly if "download-artifact@" in s["uses"]] == [
        "_site",
        "_site/preview",
    ]


def test_site_chain_runs_without_a_release(ci: dict) -> None:
    """Sans if, un job est sauté dès qu'un job en amont (même indirect) a été sauté : release
    et pypi le sont sur dev et sur main sans release, ce qui avait sauté l'assemblage et le
    déploiement du site. Toute la chaîne du site vérifie donc ses needs avec always()."""
    jobs = ci["jobs"]
    chain = {"site-prod", "site-preview"}
    chain |= {name for name in jobs if ancestors(jobs, name) & chain}
    assert chain == {"site-prod", "site-preview", "site", "deploy", "notify-site"}
    for name in chain:
        condition = " ".join(str(jobs[name].get("if", "")).split())
        assert condition.startswith("always()"), name
        for need in needs(jobs[name]):
            assert f"needs.{need}.result" in condition, (name, need)
