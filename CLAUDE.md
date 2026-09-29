# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projet

`hwbench` est un outil en ligne de commande pour Linux (Windows plus tard) qui affiche les composants d'une machine avec leurs détails importants et lance des benchmarks notés : CPU single-core, CPU multi-core, GPU, et un score combiné. Trois usages visés : diagnostic perso, projet portfolio propre, comparaison de machines entre elles.

Machine de dev : Fedora 44, Python 3.11+, shell fish.

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
```

## Conventions établies (phase 1)

- Layout `src/hwbench/`. Les modèles publics sont dans `models.py` ; `collect.py` orchestre les collecteurs et produit `(MachineSnapshot, Identifiers | None)`.
- Tout accès système des collecteurs Linux passe par `collectors/linux/_exec.py` (`run_text`, `run_json`, `read_sysfs`, `list_dir`, `which`, `is_root`). Ne jamais appeler `subprocess`/`open` directement dans un collecteur, et appeler via `_exec.xxx` (pas `from _exec import xxx`) pour que le mock fonctionne.
- Un collecteur s'enregistre avec `@register("Linux")` et implémente `collect(include_identifiers=False) -> ComponentResult(data, identifiers)`. Sans `include_identifiers`, il ne lit **aucun** fichier/champ d'identifiant (testé via `FakeSystem.paths_read`).
- Les identifiants vivent dans `BoardIdentifiers`/`RamModuleIdentifiers`/`DiskIdentifiers`, agrégés dans `Identifiers`, jamais référencés par `MachineSnapshot`. `privacy.scrub()` est un filet appliqué à toute sortie JSON.
- Donnée absente = `None`. Quand la cause compte pour l'utilisateur, le modèle porte un `Unavailable` (`NEEDS_ROOT`, `TOOL_MISSING`, `NO_DATA`) ; l'affichage traduit, il n'interroge jamais le système.
- Tests : `tests/conftest.py` fournit `FakeSystem` (fixtures `fake_system`, `laptop`) qui remplace `_exec` à partir de `tests/fixtures/`. Les fichiers `sysfs_*.json` sont des arborescences `chemin -> contenu`.
- Fixtures : repo public. Tout serial/UUID/asset tag doit contenir `FAKE`, valoir l'UUID nul, ou un id numérique à 0. `tests/test_fixtures_privacy.py` le vérifie, et vérifie aussi qu'aucun identifiant de la machine qui lance les tests n'apparaît dans les fixtures.

## Architecture

```
src/hwbench/
├── models.py          # dataclasses publiques + structures d'identifiants séparées
├── collect.py         # orchestration des collecteurs
├── display/           # rendu rich (consomme uniquement les dataclasses)
├── collectors/        # un module par composant : cpu, ram, gpu, disk, board, sensors, power
│   ├── linux/_exec.py  # seul point d'accès système (LC_ALL=C, timeout, which)
│   ├── base.py         # interface commune + registre, choix de l'implémentation selon l'OS
│   ├── linux/
│   └── windows/        # vide pour l'instant, mais l'interface doit le permettre
├── benchmarks/
│   ├── base.py         # class Benchmark : name, category (cpu_single|cpu_multi|gpu), version, is_available(), run() -> Result
│   ├── native/          # tests maison
│   └── external/        # wrappers d'outils existants via subprocess + parsing
├── scoring.py          # normalisation + score combiné pondéré
├── privacy.py          # filtrage des identifiants
├── export.py           # export/import JSON versionné
├── cli.py
└── tests/
```

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
| Batterie + secteur (`power.py`) | `/sys/class/power_supply/` | non |

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
hwbench bench [cpu-single|cpu-multi|gpu|all] [--backend ...] [--runs N]
hwbench backends          # liste les backends et leur disponibilité
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
