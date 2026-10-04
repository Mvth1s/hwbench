#!/usr/bin/env bash
# Reproduit la CI en local, à lancer avant chaque merge dans dev.
#
# Usage : scripts/ci-local.sh [base]      (base des commits à vérifier, défaut : dev)
#
# Comme .github/workflows/ci.yml : venv neuf (rien ne vient du .venv de dev),
# pip install -e '.[dev]', ruff check, ruff format --check, pytest --cov. Et comme
# commitlint.yml : commitlint sur les commits de la branche depuis <base>.
# GITHUB_ACTIONS=true et CI=true comme sur les runners : certaines bibliothèques changent de
# comportement (Typer force alors un rendu de terminal, avec codes ANSI, dans l'aide).
# Seule différence restante : la version de Python locale, la CI teste 3.11 à 3.14.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="${1:-dev}"
VENV="$(mktemp -d)"
trap 'rm -rf "$VENV"' EXIT

cd "$REPO"
export GITHUB_ACTIONS=true CI=true

echo "== venv neuf ($(python3 --version))"
python3 -m venv "$VENV"
"$VENV/bin/pip" install -q -e '.[dev]'

echo "== ruff"
"$VENV/bin/ruff" check .
"$VENV/bin/ruff" format --check .

echo "== pytest --cov"
"$VENV/bin/pytest" --cov --cov-report=term -q

if [[ "$(git rev-parse HEAD)" != "$(git rev-parse "$BASE")" ]]; then
    echo "== commitlint ($BASE..HEAD)"
    npx --yes -p @commitlint/cli@21.2.3 -p @commitlint/config-conventional@21.2.3 \
        commitlint --from "$BASE" --to HEAD
fi

echo "== CI locale OK"
