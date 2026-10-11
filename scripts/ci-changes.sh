#!/usr/bin/env bash
# Filtre « documentation seule » de la CI (.github/workflows/ci.yml, job changes).
#
# Usage : scripts/ci-changes.sh BASE HEAD
#
# Écrit « code=false » si tous les fichiers modifiés entre BASE et HEAD sont de la
# documentation, sinon « code=true » ; puis « docs=true » si au moins un fichier .md est
# modifié (contrôle des liens), sinon « docs=false ». Documentation : *.md à n'importe quel
# niveau (dont CLAUDE.md), docs/**, LICENSE. Pour une PR, BASE est la base de la PR et la
# comparaison part de leur ancêtre commun (BASE...HEAD), comme l'onglet « Files changed ».
# BASE vide, nul (premier push d'une branche) ou absent de l'historique : code=true et
# docs=true (on ne sait pas, tout tourne).
# Noms de fichiers lus par -z : un nom avec espace ou retour à la ligne ne casse rien.
set -euo pipefail

BASE="${1:-}"
HEAD="${2:?usage : ci-changes.sh BASE HEAD}"

if [[ -z "$BASE" || "$BASE" =~ ^0+$ ]] || ! git cat-file -e "${BASE}^{commit}" 2>/dev/null; then
    printf 'code=true\ndocs=true\n'
    exit 0
fi

# liste dans un fichier, pas par < <(…) : un échec de git diff (ancêtre commun introuvable)
# doit arrêter le script (set -e), pas laisser une liste vide qui passerait pour « doc seule »
LIST="$(mktemp)"
trap 'rm -f "$LIST"' EXIT
git diff -z --name-only "$BASE...$HEAD" >"$LIST"

code=false
docs=false
while IFS= read -r -d '' path; do
    case "$path" in
        *.md) docs=true ;;
        docs/* | LICENSE) ;;
        *) code=true ;;
    esac
done <"$LIST"

printf 'code=%s\ndocs=%s\n' "$code" "$docs"
