# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projet

`hwbench` est un outil en ligne de commande pour Linux (Windows plus tard) qui affiche les composants d'une machine avec leurs détails importants et lance des benchmarks notés : CPU single-core, CPU multi-core, GPU, et un score combiné. Trois usages visés : diagnostic perso, projet portfolio propre, comparaison de machines entre elles.

Machines de dev (Python 3.11+, shell fish) :
- Desktop B850 (Ryzen 7 8700F, Radeon RX 9070 XT) sous EndeavourOS : **machine de référence du scoring** (mesures stables, CV ≤ 1,3 %, pas de batterie ni de profil d'énergie, toujours disponible), sysbench, glmark2 et vkmark installés, fixtures des outils externes capturées ici.
- Dell Latitude 5420 sous Fedora 44 : portable de test (batterie, platform_profile, Intel).

## Méthode de travail

1. Commencer par proposer un plan et l'arborescence, puis attendre validation avant d'écrire du code.
2. Avancer phase par phase (voir « Phases »). À la fin de chaque phase : tests qui passent, commit, court récap de ce qui a été fait et de ce qui reste, puis attendre le feu vert avant la phase suivante.
3. Poser une question si un choix d'architecture n'est pas couvert ici, plutôt que de supposer.

## Stack

- Python 3.11+, packaging via `pyproject.toml`, installable en `pipx install .`
- `typer` pour les commandes, `rich` pour l'affichage
- `psutil` et `py-cpuinfo` pour la collecte de base
- `pytest` pour les tests, `ruff` pour le lint
- `textual` réservé à la future TUI (pas dans cette itération)

## Commandes

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest                                   # toute la suite
.venv/bin/pytest tests/test_collectors_disk.py::test_smart_health   # un seul test
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/hwbench info            # essai réel (sudo pour dmidecode/smartctl)
.venv/bin/hwbench bench cpu-single   # ~7 s ; multi-cœur jusqu'à ~90 s de warm-up sur portable
.venv/bin/hwbench bench gpu          # ~2 min 30 (glmark2 ~2 min, vkmark ~30 s)
.venv/bin/hwbench backends
scripts/capture_tool_fixtures.sh     # bash : sorties réelles de sysbench/glmark2/vkmark
python3 scripts/discord_notify.py --help   # notifications Discord (workflows uniquement)
```

Outils (shell de l'agent) : le shell des commandes est **zsh**, qui ne découpe pas les variables non quotées (`for c in $LISTE` fait un seul tour, `-b $ARGS` passe un seul argument). Toute boucle sur une liste contenue dans une variable, et tout passage d'arguments construits, se fait dans `bash -c '…'` (ou avec des tableaux bash). Enchaîner par `&&` (jamais `;`) quand une étape conditionne la suivante, en particulier avant un merge. Ne jamais filtrer par un pipe (`… | grep`, `| tail`) une commande dont le code de retour conditionne la suite : le code d'un pipeline est celui de la dernière commande, l'échec serait masqué. Lancer `scripts/ci-local.sh` tel quel avant `&& git merge`. `git cherry-pick` n'a pas d'option `-q`.

Git : une branche par phase (ou lot de corrections) depuis `dev`, un commit par fonction
ajoutée ou modifiée, merge dans `dev` à la fin. Ne pas réécrire l'historique déjà poussé.

Commits : **conventional commits** depuis `3a07904` (`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `refactor:`, `chore:`), en anglais. Pas de pied `BREAKING CHANGE` sans décision explicite (en 0.x, `major_on_zero = false` le garde en mineure, mais il change le message de release). `.github/workflows/commitlint.yml` vérifie les commits des PR depuis `max(base, CONVENTIONAL_SINCE)` (les commits antérieurs à la convention ne sont pas vérifiés).

- **Sujet en minuscule après le type**, même s'il commence par un sigle ou un nom propre : commitlint (`subject-case`) refuse `ci: Dependabot …` ou `docs: GPU …` (arrivé 3 fois). Commencer par un verbe : `ci: add Dependabot …`, `docs: describe the GPU …`.
- **Avant tout merge**, lancer commitlint sur les nouveaux commits de la branche (inclus dans `scripts/ci-local.sh`), et **s'arrêter s'il échoue** (corriger les messages tant que rien n'est poussé, jamais merger malgré l'échec) :

  ```sh
  npx --yes -p @commitlint/cli@21.2.3 -p @commitlint/config-conventional@21.2.3 \
    commitlint --from dev --to HEAD
  ```

Release : `.github/workflows/release.yml`, python-semantic-release sur push de `main` (config `[tool.semantic_release]` du `pyproject.toml`) : version dans `pyproject.toml` et `src/hwbench/__init__.py`, `CHANGELOG.md` (mode `update`, insertion au marqueur `<!-- version list -->`, l'historique antérieur aux conventional commits reste dessous), commit `chore(release): X.Y.Z`, tag `vX.Y.Z`, GitHub Release + wheel/sdist. Si une release est créée : attestation de provenance (`actions/attest-build-provenance`, `dist/*`), puis job séparé `pypi` (environnement GitHub « pypi » avec Required reviewers, `id-token: write` seul) qui publie par trusted publishing (`pypa/gh-action-pypi-publish`). Workflow sans permission par défaut, chaque job déclare le minimum. **Toute action, y compris `actions/*`, dans tous les workflows, est épinglée par SHA de commit complet (40 caractères), avec le tag exact en commentaire** (`actions/checkout@<sha> # v7.0.1`, jamais `@v7`). Le SHA est vérifié par l'API (`gh api repos/<owner>/<action>/git/ref/tags/<tag>` ; si `object.type` vaut `tag`, déréférencer jusqu'au commit) et le commentaire porte le tag précis (`v7.0.1`), pas le majeur. Dependabot met à jour SHA et commentaire. Ne jamais publier soi-même (PyPI, Pages, release). Après une release, fusionner `main` dans `dev` (le commit de release n'existe que sur `main`). Captures du README : `scripts/readme_screenshots.py` ; le README est aussi la page PyPI, donc images et liens de fichiers en URL absolues.

Dependabot (`.github/dependabot.yml`) : github-actions (`ci(deps)`) et pip (`build(deps)`, `build(deps-dev)`), PR hebdomadaires vers `dev`. CLI : `hwbench --version`, complétion Typer (`--install-completion` / `--show-completion`, shell détecté d'après le processus parent). Couverture : `pytest --cov` (config `[tool.coverage]`), tableau markdown dans le résumé du job CI. Licence **AGPL-3.0-or-later** depuis la version qui suit la 0.3.0 (0.1.0 à 0.3.0 restent MIT) : `LICENSE` = texte officiel de gnu.org non modifié, précédé de la seule ligne `Copyright (c) 2026 Mvth1s` ; expression SPDX `AGPL-3.0-or-later` dans `pyproject.toml` (PEP 639 : aucun classifieur `License ::`). Toute nouvelle dépendance doit avoir une licence compatible AGPL v3 (permissives MIT/BSD/ISC/Apache-2.0, LGPL/GPL v3) : vérifier avec `pip-licenses` dans un venv jetable. Les fichiers de `results/` sont des données publiées sous CC0-1.0 (CONTRIBUTING.md), pas sous AGPL.

**Avant chaque merge dans `dev` : `scripts/ci-local.sh`** (et s'arrêter s'il échoue). Il reproduit la CI : venv neuf, `pip install -e '.[dev]'`, ruff check + format, `pytest --cov`, commitlint sur `dev..HEAD`, avec `GITHUB_ACTIONS=true` et `CI=true` comme sur les runners. Le `.venv` de dev et l'environnement local ne suffisent pas : sous GitHub Actions, Typer force un rendu de terminal (aide avec codes ANSI), ce qui a cassé un test passé en local (`--install-completion` découpé en segments colorés). Ne pas tester un texte rendu par Typer/rich quand la structure (paramètres de la commande, dataclasses) peut être testée. Seule différence restante : la CI teste aussi Python 3.11 à 3.13.

CI (`.github/workflows/ci.yml`) : ruff + pytest sur Python 3.11 à 3.14 (ubuntu-latest). Pas d'installation de Python supplémentaire en local (pas de `uv python install`) : la compatibilité 3.11 est vérifiée par la CI.

## Conventions établies (phase 1)

- Layout `src/hwbench/`. Les modèles publics sont dans `models.py` ; `collect.py` orchestre les collecteurs et produit `(MachineSnapshot, Identifiers | None)`.
- Tout accès système des collecteurs Linux passe par `collectors/linux/_exec.py` (`run_text`, `run_json`, `read_sysfs`, `exists`, `list_dir`, `which`, `is_root`). Ne jamais appeler `subprocess`/`open` directement dans un collecteur, et appeler via `_exec.xxx` (pas `from _exec import xxx`) pour que le mock fonctionne.
- Un collecteur s'enregistre avec `@register("Linux")` et implémente `collect(include_identifiers=False) -> ComponentResult(data, identifiers)`. Sans `include_identifiers`, il ne lit **aucun** fichier/champ d'identifiant (testé via `FakeSystem.paths_read`).
- Les identifiants vivent dans `BoardIdentifiers`/`RamModuleIdentifiers`/`DiskIdentifiers`, agrégés dans `Identifiers`, jamais référencés par `MachineSnapshot`. `privacy.scrub()` est un filet appliqué à toute sortie JSON.
- Identifiants carte mère (`IdentifierValue`) : `str` = valeur, `None` = vide ou valeur bidon (« non renseigné »), `Unavailable.NEEDS_ROOT` = fichier présent mais illisible sans root, `Unavailable.NO_DATA` = absent. `Unavailable` est un `StrEnum` : tester `isinstance(v, Unavailable)` **avant** de le traiter comme une chaîne. `FakeSystem(unreadable=...)` simule un fichier présent mais illisible.
- Affichage rich en français : nombres via `display/fmt.py` (`num`, `compact`, virgule décimale), libellés système traduits dans `display/` (ex. statut batterie). Les modèles et le JSON gardent les valeurs brutes (nombres standard, dates ISO, statuts sysfs en anglais). Les libellés fabricant (nom CPU, version OpenGL) ne sont jamais reformatés.
- Fabricants RAM : `collectors/jedec.py` (indépendant de l'OS) décode les codes JEP106 ; code brut conservé si inconnu. Chaque entrée cite sa révision JEP106 en commentaire ; pas d'entrée non sourcée.
- Benchmarks (phase 2) : `Benchmark.run()` renvoie **une** `Measurement` ; `runner.run_benchmark(bench, RunSettings)` fait le warm-up adaptatif + runs (≥ 3), médiane, écart-type, avertissements, et relève l'état via `machine_state.capture_state` (seul pont vers les collecteurs). Modèles dans `results.py` ; avertissements stockés en codes (`BenchWarning`), traduits dans `display/bench.py`.
- Warm-up adaptatif : itérations jusqu'à 2 consécutives à ≤ 3 % d'écart, plafond par catégorie (`DEFAULT_MAX_WARMUP_S` : 30 s single, 90 s multi), sinon `WARMUP_UNSTABLE`. Le 1er run à froid est `Result.burst` : affiché et exporté, **jamais** utilisé par le scoring. Tous les seuils (tolérance, plafond, CV 5 %, 70 °C) sont dans `RunSettings` et exposés en options de `hwbench bench`. Tests du runner : horloge simulée (`clock=`), jamais de vrai temps.
- État machine : `MachineState` porte governor, secteur, température, `platform_profile` (+ choix) et l'EPP de cpu0. `MachineState.throttling_settings()` décide de `POWER_PROFILE` (« performance », ou le plus performant des choix de la machine ; `custom` et absent non jugés).
- Unité du score natif : `"index"`, affichée « indice brut » ; les points viennent du scoring.
- Alimentation : sans batterie système (`scope` ≠ Device), `on_ac = True` (desktop), affiché « secteur (pas de batterie) » ; `MachineState.has_battery`.
- Capteurs : `chip` reste le nom brut hwmon (utilisé par `machine_state` pour la température CPU) ; `instance` distingue les homonymes (`nvme0` via la cible du lien `device`, sinon `spd5118 #1`…). Les captures stockent les liens sysfs sous la clé `<chemin>@link` (valeur = nom de la cible), lue par `_exec.link_name` / `FakeSystem.link_name`.
- RAM : slot = `Bank Locator / Locator` quand le Locator seul n'est pas unique ; vitesse configurée > nominale = profil EXPO/XMP.

## Conventions établies (phase 3)

- Backends externes : `benchmarks/external/`, tout accès système via `benchmarks/external/_run.py` (`which`, `getenv`, `exists`, `run`, `output_or_raise` qui lève `ToolError`). Tests : fixture autouse `no_external_tools` (aucun vrai outil n'est jamais lancé), `fake_tools(outputs=, env=, files=, failing=)` pour en simuler.
- Identité d'un backend (`BackendId`) : nom, version du protocole hwbench, version de l'outil, mode de présentation. Deux mesures ne sont comparables que si les quatre sont égaux. Le pilote GPU (`environment["driver"]`, ex. `Mesa 26.2.3-arch1.1`) n'en fait **pas** partie : information seulement. Comparaison par `results.driver_key` (nom + version amont, révision du paquet ignorée) et seulement pour un même GPU (`results.gpu_key` : nom du renderer avant « (… » ou « / », sans noyau ni DRM) : avertissement non bloquant dans `bench` (`BackendScore.driver_differs`, GPU de la référence) et `compare` (`CompareWarning.DRIVER_DIFFERS`, fichiers de même GPU) ; sur un autre GPU, simple information (`BackendScore.driver_info`). Les chaînes brutes restent celles affichées. Changer scènes, durée, résolution ou paramètres = incrémenter `*_VERSION` du module.
- GPU : 3840×2160, glmark2 `--off-screen`, vkmark `--winsys headless` (repli fenêtre + `--present-mode immediate` + `VSYNC_UNVERIFIED`). Scènes choisies par le critère ratio FPS 1080p/4K ≥ 1,8 (étude dans le README et `_gpu.py`). L'UUID GPU de vkmark n'est jamais parsé ; les fixtures le mettent à zéro.
- Scoring (`scoring.py`) : CPU = natif seul ; GPU = moyenne géométrique des backends GPU mesurés, liste identique à la référence sinon `BACKENDS_DIFFER` ; combiné sans GPU mesuré = CPU seul + `gpu_missing`. Jamais de moyenne silencieuse.
- Référence : `src/hwbench/data/reference.json` (package data), générée sur le desktop B850 par `.venv/bin/hwbench reference -o src/hwbench/data/reference.json` (session graphique, machine au repos) ; à régénérer seulement quand une version de bench ou d'outil change, jamais pour une mise à jour du pilote GPU ; `reference.py` fait les contrôles (secteur, profil, warm-up) et `--force` les inscrit dans `forced_reasons`. `tests/test_reference_file.py` vérifie le vrai fichier (3 catégories, 6 benchs, versions de protocole à jour, aucun identifiant) : incrémenter la version d'un bench impose de régénérer la référence. Les tests CLI patchent `cli.load_reference` pour ne pas dépendre du fichier. Tests du scoring : `conftest.make_result`.
- Bench natif : une classe par catégorie (`native-cpu-single`, `native-cpu-multi`), score = moyenne géométrique des débits des charges de `benchmarks/native/workloads.py`. Toute modification d'une charge change l'empreinte testée dans `tests/test_native_cpu.py` : incrémenter `NATIVE_CPU_VERSION` et mettre à jour l'empreinte. Multi-cœur : `multiprocessing` en `spawn`, barrière pour exclure démarrage et préparation du chrono, les charges passées en argument aux workers.
- Tests des benchs : `conftest.TINY` (charges minuscules) ; patcher `cpu.WORKLOADS`, `cli.capture_state` et `runner.DEFAULT_MAX_WARMUP_S` (sinon le warm-up de charges bruitées court jusqu’à 90 s).
- Donnée absente = `None`. Quand la cause compte pour l'utilisateur, le modèle porte un `Unavailable` (`NEEDS_ROOT`, `TOOL_MISSING`, `NO_DATA`) ; l'affichage traduit, il n'interroge jamais le système.
- Tests : `tests/conftest.py` fournit `FakeSystem` (fixtures `fake_system`, `laptop`) qui remplace `_exec` à partir de `tests/fixtures/`. Les fichiers `sysfs_*.json` sont des arborescences `chemin -> contenu`.
- Fixtures réelles : `scripts/capture_fixtures.sh` (lancé par l'utilisateur, sans sudo devant) écrit `tests/fixtures/<fabricant-modèle>/` anonymisé ; `tests/test_real_fixtures.py` rejoue les collecteurs sur chaque dossier avec des assertions génériques. Les fixtures écrites à la main à la racine de `tests/fixtures/` ne servent qu'aux cas limites (desktop, SATA en échec, smartctl < 7.0, dmidecode < 3.7 en « GB »).
- Fixtures : repo public. Tout serial/UUID/asset tag doit contenir `FAKE`, valoir l'UUID nul, ou un id numérique à 0. `tests/test_fixtures_privacy.py` le vérifie, et vérifie aussi qu'aucun identifiant de la machine qui lance les tests n'apparaît dans les fixtures.

## Conventions établies (phase 4)

- Export (`export.py`) : `MachineExport` (schéma `EXPORT_SCHEMA_VERSION` = 2), écrit via `privacy.scrub`, relu en dataclasses par un désérialiseur générique (`_build` : dataclasses, listes, dicts à clés d'enum, unions, enums) avec erreurs explicites nommant le fichier. Changer la forme d'un modèle exporté = incrémenter `EXPORT_SCHEMA_VERSION`. `hwbench export` lance les benchs (même session que `bench`, `_bench_session`) puis écrit le fichier.
- Référence dans l'export : `ReferenceInfo` avec `digest` (`sha256:` + 64 hex du JSON canonique). `privacy.NON_SENSITIVE_KEYS` autorise des clés connues comme non sensibles **avec le format exact de leur valeur** (`digest` : `sha256:` + 64 hex) ; une valeur non conforme sous une clé autorisée est filtrée normalement. Ajouter une clé à cette liste = ajouter son motif et un test.
- Compare (`compare.py`, logique pure ; `display/compare.py`, rendu) : premier fichier = base. Écart d'un bench seulement si même `BackendId` ; écart d'un score seulement si même empreinte de référence, même liste de backends et, pour le combiné, mêmes pondérations. Sinon la cellule garde sa valeur et porte une raison (`Incomparable`).
- Balisage rich : tout texte venu d'un fichier, du firmware ou d'un outil externe est affiché via `rich.text.Text` (ou une console `markup=False`, cas de `info`), jamais dans une chaîne interprétée : « [/x] » ferait planter rich (`MarkupError`), « [link=…] » injecterait un lien. Seuls les messages fixes du CLI utilisent du balisage.

## Conventions établies (phase B : classement)

- Module `leaderboard/` (`python -m hwbench.leaderboard validate FICHIERS…` / `site --results --out`). Validation (`validate.py`) : nom `[a-z0-9][a-z0-9-]*.json` directement dans `results/`, dossier sans lien symbolique (`resolves_to_itself`), fichier ouvert avec `O_NOFOLLOW` et lu au plus `MAX_BYTES` (`read_bounded`), JSON strict (`strict_json` : clés dupliquées et NaN refusés), `privacy.scrub` idempotent (chaque champ fautif nommé), référence = empreinte de la référence du paquet et non forcée, benchs connus à leur version de protocole (`current_versions`), scores stockés identiques entrée par entrée à ceux recalculés.
- Site (`site.py`) : HTML statique, CSS intégré, aucun JavaScript (onglets en CSS pur), points **recalculés** contre la référence du paquet (jamais repris de l'export), combiné classé seulement s'il porte sur les trois catégories, tout texte d'un export passé par `html.escape`.
- CI : `results.yml` sur `pull_request` uniquement (jamais `pull_request_target`), validateur installé depuis la branche de base et lancé avec `python -I` (le checkout de la PR ne doit pas entrer dans le chemin d'import), noms de fichiers par `git diff -z | xargs -0`, seuls les fichiers ajoutés/modifiés sont validés, échec si `results/` n'est pas un vrai dossier. `pages.yml` sur push de `main` : build (`contents: read`) puis deploy (`pages: write`, `id-token: write`), actions Pages épinglées par SHA. Une PR qui change à la fois le code (version de bench, référence) et des résultats échoue à la validation : fusionner le code d'abord.
- `results/` est public : tout export ajouté est vérifié sans identifiant (hostname, MAC, serials de la machine). `tests/test_results_dir.py` valide les vrais fichiers ; après un changement de version de bench ou de référence, re-exporter les exemples du dépôt.

## Conventions établies (phase B2 : notifications Discord)

- Natif GitHub → Discord (`/github`, webhooks du dépôt, pas d'Actions) : #commits (push, create, delete), #pull-requests, #communaute (issues, discussions, fork, watch ; pas de « star », que Discord `/github` ne gère pas). Ne pas les doubler par Actions. Tout le reste passe par `scripts/discord_notify.py`.
- `scripts/discord_notify.py` : bibliothèque standard seule (urllib), une sous-commande par message, chacune liée à **une** variable fixe (`DISCORD_WEBHOOK_CI`, `_CLASSEMENT`, `_DEPENDABOT`, `_RELEASES`, `_DEPLOIEMENTS`, `_VEILLE`, `_HEBDO`, du secret de même nom). Fonctions de construction pures, testées dans `tests/test_discord_notify.py` (chargé par `importlib`, API et envoi simulés, aucun réseau). Jamais d'échec : secret absent, API injoignable ou refus de Discord = `::warning::` et code 0 (et `continue-on-error: true` sur chaque étape). L'URL du webhook n'est jamais affichée (ni le texte des exceptions d'envoi). `allowed_mentions: {"parse": []}` sur chaque message, 429 réessayé après `retry_after` (plafond 60 s), textes tronqués aux limites Discord (`embed`, `payloads`), tout texte externe passé par `escape_md` (liens masqués, mentions, Markdown).
- Salons : #ci (échec d'un push sur dev/main de CI, Release ou Pages, jobs en cause ; retour au vert quand le run terminé précédent, ou l'essai précédent d'une relance, avait échoué ; annulés ignorés), #classement (soumission validée/refusée + nouvelles machines après déploiement), #dependabot (CI des PR de `dependabot[bot]`), #releases et #deploiements (`release.yml` : jobs `notify-release` et `notify-pypi` séparés, le job `pypi` ne contient que la publication ; `pages.yml` : job `notify`), #veille et #rapport-hebdo (`veille.yml` le jeudi, `hebdo.yml` le lundi, `workflow_dispatch` sur les deux).
- `notify.yml` (`workflow_run` sur CI, Results, Release, Pages) : jamais de checkout du code de la PR. Seul `scripts/discord_notify.py` est extrait (sparse, `persist-credentials: false`), depuis main ; il lit l'événement (`GITHUB_EVENT_PATH`) et l'API GitHub. Les `if:` ne font que des comparaisons, aucun texte d'un contributeur n'est interpolé dans `run` (passage par l'événement ou `env`). Un job par salon, avec son seul secret et ses permissions (`actions`, `checks`, `pull-requests: read`). PR d'un fork : `workflow_run.pull_requests` est vide, la PR est retrouvée par `pulls?head=propriétaire:branche` + `head.sha`.
- Raisons d'un refus au classement : le validateur écrit sous GitHub Actions une annotation `::error title=Soumission refusée::<fichier> : <problème>` par problème (`_annotation` échappe `%`, CR, LF) ; `notify.yml` les relit par l'API des check-runs (annotations `failure`, hors « Process completed with exit code »), sinon les étapes en échec. Garder ce format.
- Nouvelles machines : `pages.yml` compare `github.event.before` à HEAD (`--diff-filter=A` sur `results/*.json`, noms par `-z`/`xargs -0`), puis `python -m hwbench.leaderboard summary --results results --new …` (JSON sur une ligne : rang au classement combiné, `null` sans les trois catégories), transmis au job `notify` par output et `env` (`SUMMARY`).
- Veille : versions `pkgver` des paquets Arch (`archlinux.org/packages/search/json/?name=`) comparées aux `tool_version` de `reference.json`, matrice `python-version` de `ci.yml` (liste en ligne, seule forme lue) comparée aux versions mineures sorties d'après `endoflife.date/api/v1/products/python`. Sans état : le message revient chaque semaine tant que l'écart existe (régénérer la référence sur le B850, ou ajouter la version à la matrice). Hebdo : pypistats (`recent`, `last_week`), API GitHub (étoiles, recherche PR/issues ouvertes, dernier run `ci.yml` en push sur main et dev, dernière release), nombre de fichiers `results/*.json` ; une source en panne = « non disponible ».
- **Secrets et Dependabot** (doc GitHub vérifiée le 09/10/2026) : les runs déclenchés par Dependabot via `push`, `pull_request`, `pull_request_review` et `pull_request_review_comment` sont traités comme venant d'un fork (jeton en lecture seule, **secrets Dependabot seulement**). `workflow_run` n'est pas dans cette liste, et sa documentation précise que le workflow lancé « is able to access secrets and write tokens, even if the previous workflow was not » : le job `dependabot` de `notify.yml` reçoit donc les **secrets Actions**. `DISCORD_WEBHOOK_DEPENDABOT` existe aussi en secret Dependabot, sous le même nom, par précaution : `secrets.DISCORD_WEBHOOK_DEPENDABOT` se résout dans les deux cas. En cas de rotation du webhook, mettre à jour les deux. À confirmer sur la première PR Dependabot après la release (un avertissement « secret absent » dans le run Notify indiquerait le contraire).
- **`workflow_run` et `schedule` ne tournent que depuis main**, la branche par défaut (vérifié : `gh repo view --json defaultBranchRef`). Doc GitHub : ces événements ne déclenchent un workflow que si son fichier existe sur la branche par défaut, `workflow_run` prend `GITHUB_SHA` = dernier commit de la branche par défaut, et les workflows planifiés tournent sur le dernier commit de la branche par défaut. Conséquences : `notify.yml`, `veille.yml` et `hebdo.yml` ne s'activent qu'après la release qui les amène sur main ; une modification de ces fichiers sur dev n'a aucun effet avant la release suivante ; un run de CI sur dev déclenche la version de `notify.yml` présente sur main (et le script extrait est celui de main). Tester une version de dev : `gh workflow run veille.yml --ref dev` (possible une fois le fichier présent sur main).

## Architecture

```
src/hwbench/
├── models.py          # dataclasses publiques + structures d'identifiants séparées
├── collect.py         # orchestration des collecteurs
├── display/           # rendu rich (consomme uniquement les dataclasses)
├── collectors/        # un module par composant : cpu, ram, gpu, disk, board, sensors, power
│   ├── base.py         # interface commune + registre, choix de l'implémentation selon l'OS
│   ├── jedec.py        # décodage JEP106, indépendant de l'OS
│   ├── linux/          # _exec.py = seul point d'accès système (LC_ALL=C, timeout, which)
│   └── windows/        # vide pour l'instant, mais l'interface doit le permettre
├── benchmarks/
│   ├── base.py         # Benchmark (name, category, backend, version, unit, is_available(), run() -> Measurement) + registre @register
│   ├── native/          # tests maison
│   └── external/        # sysbench, glmark2, vkmark ; _run.py = seul accès système, _gpu.py = conditions GPU
├── results.py          # Category, BenchWarning, Measurement, MachineState, Result
├── runner.py           # warm-up, runs, médiane/écart-type, avertissements -> Result
├── machine_state.py    # governor, secteur, température : seul pont benchmarks -> collecteurs
├── scoring.py          # normalisation (référence = 1000), catégories, score combiné pondéré
├── privacy.py          # filtrage des identifiants
├── export.py           # export JSON versionné et relecture en dataclasses
├── compare.py          # comparaison d'exports (cellules, écarts, raisons de non-comparabilité)
├── reference.py        # contrôles et génération du fichier de référence
├── leaderboard/        # classement : validate.py (soumissions), site.py (site statique)
├── data/reference.json # référence du scoring (package data, générée)
└── cli.py
tests/                  # hors de src/, fixtures dans tests/fixtures/ (tools/ = outils externes)
```

`benchmarks.base.benchmark_classes()` importe `hwbench.benchmarks.native` et `hwbench.benchmarks.external` pour peupler le registre : un nouveau module de backend doit être importé dans le `__init__.py` de son paquet, sinon ses classes n'apparaissent pas.

Séparation stricte : collecte, benchmark, scoring et affichage ne dépendent pas les uns des autres. L'affichage consomme des dataclasses, jamais la sortie brute d'une commande. La future TUI et le futur support Windows ne doivent être qu'une couche en plus.

## Collecte des composants (Linux)

Règle générale : jamais de parsing de sortie texte « humaine » quand une sortie structurée existe. Priorité à `/sys` et `/proc`, ensuite aux commandes avec sortie JSON, et le parsing texte seulement en dernier recours.

| Composant | Source | Root |
|---|---|---|
| CPU | `lscpu -J`, `/proc/cpuinfo`, `/sys/devices/system/cpu/` (fréquences, governor) | non |
| RAM totale | `/proc/meminfo` ou psutil | non |
| Barrettes RAM | `dmidecode -t memory` (parsing texte, pas de JSON) | oui |
| Machine, carte mère, BIOS | `/sys/class/dmi/id/*` | non (sauf serials) |
| GPU | `lspci -mm -nn`, puis `glxinfo -B`, `vulkaninfo --summary`, `nvidia-smi` si présent | non |
| Disques | `lsblk -J -b -o NAME,SIZE,MODEL,TYPE,ROTA,TRAN` (`-b` : tailles en octets) | non |
| Santé disque | `smartctl -j -a <device>` (vérifie le support de `-j` sur la version installée) | oui |
| Températures, ventilos | `/sys/class/hwmon/` ou `psutil.sensors_temperatures()` | non |
| Batterie + secteur (`power.py`) | `/sys/class/power_supply/`, `/sys/firmware/acpi/platform_profile{,_choices}` | non |
| EPP | `/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference` | non |

Exigences :
- Lancer toutes les commandes externes avec `LC_ALL=C`, sinon la locale française met des virgules dans les nombres (constaté : `lscpu` renvoie `4400,0000`).
- Vérifier la présence de chaque outil avec `shutil.which` et chaque fichier avant lecture.
- Dégradation propre : sans root, sans outil, ou sans capteur, le champ vaut `None` et l'affichage indique « non disponible » ou « relancer avec sudo ». Aucun crash.
- `inxi` n'est pas une dépendance. Il peut exister plus tard comme source optionnelle, pas comme socle.
- Chaque collecteur a des tests unitaires avec des fixtures (sorties réelles enregistrées dans `tests/fixtures/`), sans exécuter les commandes.

## Vie privée

Filtrer dès la collecte, pas seulement à l'export : numéros de série (disques, RAM, système, carte mère), UUID produit, EUI-64/NGUID NVMe, adresses MAC, hostname, asset tags. Ils ne doivent jamais apparaître dans un objet de données. Une option `--show-serials` peut les afficher à l'écran en local uniquement, jamais dans un export. Tester ce filtrage. `--json` et `--show-serials` sont incompatibles (erreur explicite, code 2).

## Benchmarks

Interface unique : un backend natif ou externe renvoie le même `Result` (valeur brute, unité, « plus haut = mieux », durée, version du bench, backend utilisé). L'utilisateur choisit avec `--backend native|<outil>|all`.

Natifs :
- CPU single-core : charges déterministes (hashing via hashlib, compression zlib/lzma, un calcul numérique).
- CPU multi-core : la même charge sur N workers avec `multiprocessing` (surtout pas `threading`, à cause du GIL), N = nombre de CPU logiques par défaut.
- GPU natif : hors périmètre pour l'instant. Le GPU passe par les backends externes.

Externes, chacun avec `is_available()` : `sysbench cpu` (single et multi), `glmark2` ou `glmark2-wayland`, `vkmark`. Parsing robuste, tests sur fixtures.

Fiabilité des mesures :
- warm-up puis au moins 3 runs, score = médiane, écart-type conservé dans le résultat
- relever l'état de la machine dans le résultat : governor CPU, sur secteur ou sur batterie, température CPU avant et après
- avertir (sans bloquer) si la machine est sur batterie ou si la température de départ est élevée

## Scoring

- Chaque bench est normalisé par rapport à une machine de référence qui vaut 1000 points. La référence est un fichier JSON versionné dans le repo.
- Score combiné = moyenne géométrique pondérée des catégories, pondérations configurables. Si le GPU est absent, le score combiné est calculé sans lui et le signale.
- Chaque bench porte une version. Deux résultats de versions différentes sont déclarés non comparables.

## Export et comparaison

- `hwbench export -o machine.json` : schéma JSON avec `schema_version`, date au format ISO, composants filtrés, résultats de bench.
- `hwbench compare a.json b.json [c.json...]` : tableau rich côte à côte, écarts en pourcentage, et avertissement si les versions de bench diffèrent.

## Commandes CLI

```
hwbench info [--json] [--show-serials]
hwbench bench [cpu-single|cpu-multi|gpu|all] [--backend ...] [--runs N] [--weights ...]
hwbench backends          # liste les backends et leur disponibilité
hwbench reference -o FILE [--force]   # machine de référence uniquement
hwbench export -o FILE
hwbench compare FILES...
```

## Phases

1. Squelette du projet, collecteurs Linux, `hwbench info` avec affichage rich, filtrage vie privée, tests.
2. Interface Benchmark, benchs CPU natifs single et multi, `hwbench bench`.
3. Backends externes (sysbench, glmark2, vkmark), `hwbench backends`, scoring et score combiné.
4. Export JSON et `compare`.

Hors périmètre pour cette itération, mais l'architecture doit les permettre : TUI Textual, support Windows (WMI/CIM), classement en ligne avec une API.

## Qualité

- Type hints partout, dataclasses pour les modèles.
- README avec installation, exemples de sortie, et dépendances système optionnelles pour Fedora et Debian/Ubuntu.
- Aucune commande qui modifie le système. Si un outil manque, on l'indique avec la commande d'installation suggérée, sans l'installer automatiquement.
