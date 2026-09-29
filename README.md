# hwbench

Outil en ligne de commande pour Linux qui inventorie les composants d'une machine et lance des
benchmarks (CPU single-core, CPU multi-core, et à terme GPU et score combiné) pour comparer des
machines entre elles.

> État : phase 2. `hwbench info` et les benchmarks CPU natifs (`hwbench bench`) sont
> disponibles ; backends externes, GPU, scoring, export et comparaison arrivent ensuite.

## Installation

Python 3.11 ou plus récent.

```sh
pipx install .
```

Pour développer :

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
```

Pour ajouter une machine aux fixtures de test (sorties réelles, identifiants anonymisés) :

```sh
scripts/capture_fixtures.sh [nom]     # sans sudo : il le demande lui-même pour dmidecode/smartctl
```

## Utilisation

```sh
hwbench info                  # tableau récapitulatif
hwbench info --json           # sortie JSON, sans aucun identifiant
hwbench info --show-serials   # affiche serials / UUID / hostname à l'écran, localement
```

`--json` et `--show-serials` sont incompatibles : les identifiants ne sortent jamais de l'écran.

### Avec root (barrettes RAM et santé SMART)

`dmidecode` et `smartctl` demandent root. Or `sudo` utilise son propre `PATH` (`secure_path`),
qui ne contient ni `~/.local/bin` (pipx) ni le venv : `sudo hwbench` répond « command not found ».
Passe le chemin complet :

```sh
sudo "$(command -v hwbench)" info     # bash, zsh, et fish ≥ 3.4
sudo (command -v hwbench) info        # fish < 3.4
sudo .venv/bin/hwbench info           # depuis le repo, en développement
```

Exemple (sans root) :

```
╭─ CPU ────────────────────────────────────────────────────────────────────────╮
│ Modèle               11th Gen Intel(R) Core(TM) i5-1145G7 @ 2.60GHz          │
│ Cœurs / threads      4 / 8                                                   │
│ Fréquence min / max  400 MHz / 4400 MHz                                      │
│ Fréquence actuelle   moy. 1827 MHz (min 401, max 3939)                       │
│ Governor             performance                                             │
│ Caches               L1d 192 Kio · L1i 128 Kio · L2 5 Mio · L3 8 Mio         │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Mémoire ────────────────────────────────────────────────────────────────────╮
│ Total      15.3 Gio                                                          │
│ Barrettes  relancer avec sudo                                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Disques ────────────────────────────────────────────────────────────────────╮
│  Nom      Modèle                        Taille     Type  Bus   SMART         │
│  nvme0n1  Samsung SSD 990 EVO Plus 1TB  931.5 Gio  SSD   nvme  relancer avec │
│                                                                sudo          │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## Benchmarks

```sh
hwbench bench                          # toutes les catégories, tous les backends disponibles
hwbench bench cpu-single               # une seule catégorie : cpu-single, cpu-multi, gpu, all
hwbench bench cpu-multi --workers 4    # nombre de processus (défaut : CPU logiques)
hwbench bench --backend native --runs 5
```

### Backend natif (CPU)

Quatre charges déterministes, identiques sur toutes les machines, dont le temps est passé dans du
code C (pour limiter l'effet de la version de Python) : SHA-256 (OpenSSL), compression zlib
niveau 6, compression LZMA preset 1, exponentiation modulaire 2048 bits (entiers de CPython).
Le score est la moyenne géométrique des débits des quatre charges ; le détail par charge est
affiché. Le multi-cœur lance la même charge dans N processus (`multiprocessing`, pas de threads
à cause du GIL) et additionne leurs débits. Les versions de Python, OpenSSL, zlib et liblzma
sont relevées avec chaque résultat.

### Fiabilité des mesures

Chaque bench fait un warm-up puis au moins 3 runs ; le score est la médiane, l'écart-type est
conservé. Le governor CPU, l'alimentation (secteur ou batterie) et la température CPU sont
relevés avant et après. hwbench avertit, sans bloquer, si la machine est sur batterie, si le
CPU dépasse 70 °C au départ, ou si les runs varient de plus de 5 %.

Sur un portable, le multi-cœur est souvent instable : le CPU tient un turbo court (PL2) puis
redescend à sa puissance soutenue (PL1). Laisser refroidir la machine et la brancher sur secteur
avant de mesurer.

```
╭─ CPU single-core · native v1 ────────────────────────────────────────────────╮
│ Score (médiane)  89,8 pts  ± 0,4 (CV 0,5 %)                                  │
│ Runs             89,8 · 90,2 · 89,3  (+ 1 warm-up, 6,9 s au total)           │
│ Governor         performance                                                 │
│ Alimentation     secteur                                                     │
│ Température CPU  70 °C avant → 71 °C après                                   │
│  Charge                                   Médiane                            │
│  SHA-256                             1624,2 Mio/s                            │
│  Compression zlib (niveau 6)           79,2 Mio/s                            │
│  Compression LZMA (preset 1)           12,0 Mio/s                            │
│  Exponentiation modulaire 2048 bits     42,3 op/s                            │
│ CPython 3.14.7 · OpenSSL 3.5.8 25 Aug 2026 · zlib 1.3.1.zlib-ng · liblzma    │
│ 5.8.2                                                                        │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## Dépendances système optionnelles

Aucune n'est obligatoire : si un outil manque, le champ correspondant est affiché
« non disponible » ou « outil absent », sans erreur. hwbench n'installe jamais rien lui-même.

| Outil | Sert à | Fedora | Debian / Ubuntu |
|---|---|---|---|
| `lscpu`, `lsblk` | CPU, disques | `util-linux` (déjà présent) | `util-linux` (déjà présent) |
| `lspci` | GPU (PCI) | `sudo dnf install pciutils` | `sudo apt install pciutils` |
| `glxinfo` | GPU (OpenGL) | `sudo dnf install glx-utils` | `sudo apt install mesa-utils` |
| `vulkaninfo` | GPU (Vulkan) | `sudo dnf install vulkan-tools` | `sudo apt install vulkan-tools` |
| `nvidia-smi` | GPU NVIDIA | fourni par le pilote propriétaire | fourni par le pilote propriétaire |
| `dmidecode` | barrettes RAM (root) | `sudo dnf install dmidecode` | `sudo apt install dmidecode` |
| `smartctl` ≥ 7.0 | santé des disques (root) | `sudo dnf install smartmontools` | `sudo apt install smartmontools` |

## Vie privée

Numéros de série (disques, RAM, système, carte mère), UUID produit, EUI-64/NGUID/WWN des
disques, asset tags et hostname ne sont pas lus par défaut et ne font jamais partie des données
collectées. Seul `--show-serials` les lit, dans une structure séparée, pour l'affichage local.
Toute sortie JSON passe en plus par un filtre de sécurité (`privacy.py`).
