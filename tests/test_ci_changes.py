"""scripts/ci-changes.sh : filtre « documentation seule » de la CI, sur un vrai dépôt git."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ci-changes.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("bash") is None, reason="git et bash requis"
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(repo: Path, files: dict[str, str]) -> str:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, "utf-8")
    git(repo, "add", "--all")
    git(repo, "commit", "-q", "--allow-empty", "-m", "change")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "dev")
    git(tmp_path, "config", "user.email", "ci@example.invalid")
    git(tmp_path, "config", "user.name", "ci")
    git(tmp_path, "config", "commit.gpgsign", "false")
    commit(tmp_path, {"README.md": "a", "src/hwbench/cli.py": "a", "results/x.json": "{}"})
    return tmp_path


def changes(repo: Path, base: str, head: str = "HEAD") -> str:
    out = subprocess.run(
        ["bash", str(SCRIPT), base, head], cwd=repo, check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


@pytest.mark.parametrize(
    "files",
    [
        {"README.md": "b"},
        {"CLAUDE.md": "b", "CONTRIBUTING.md": "b"},
        {"docs/rapport.md": "b", "docs/image.png": "b"},
        {"LICENSE": "b"},
        {"tests/fixtures/report/README.md": "b"},
        {"docs/avec espace\net retour.md": "b"},
        {},
    ],
)
def test_documentation_only(repo: Path, files: dict[str, str]) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, files)
    assert changes(repo, base) == "code=false"


@pytest.mark.parametrize(
    "files",
    [
        {"src/hwbench/cli.py": "b"},
        {"README.md": "b", "pyproject.toml": "b"},
        # une soumission au classement redéploie le site : ce n'est pas de la documentation
        {"results/y.json": "{}"},
        {".github/workflows/ci.yml": "b"},
        {"LICENSE.txt": "b"},
        {"docsx/a.md.txt": "b"},
    ],
)
def test_code_changes(repo: Path, files: dict[str, str]) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, files)
    assert changes(repo, base) == "code=true"


def test_pull_request_compares_from_the_common_ancestor(repo: Path) -> None:
    """Un changement de code arrivé sur la base après le départ de la PR ne compte pas."""
    fork = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "doc")
    commit(repo, {"README.md": "b"})
    git(repo, "checkout", "-q", "dev")
    base = commit(repo, {"src/hwbench/cli.py": "b"})
    assert changes(repo, base, "doc") == "code=false"
    assert git(repo, "merge-base", base, "doc") == fork


@pytest.mark.parametrize("base", ["", "0000000000000000000000000000000000000000", "f" * 40])
def test_unknown_base_runs_everything(repo: Path, base: str) -> None:
    commit(repo, {"README.md": "b"})
    assert changes(repo, base) == "code=true"


def test_git_failure_is_an_error_not_a_documentation_change(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, {"README.md": "b"})
    result = subprocess.run(
        ["bash", str(SCRIPT), base, "branche-inexistante"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "code=" not in result.stdout
