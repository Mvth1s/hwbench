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
hwbench bench cpu-multi --max-warmup 180   # plafond du warm-up en secondes
hwbench bench --max-cv 3 --hot-start 60    # seuils des avertissements (défaut : 5 %, 70 °C)
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

Warm-up adaptatif : le bench enchaîne les itérations jusqu'à ce que deux consécutives soient à
moins de 3 % l'une de l'autre (`--warmup-tolerance`), dans la limite d'un plafond de 30 s en
single-core et 90 s en multi-cœur (`--max-warmup`). Si le plafond est atteint sans stabilité,
hwbench l'indique. Suivent au moins 3 runs mesurés ; le score est leur médiane, l'écart-type est
conservé.

Le premier run, à froid, est gardé à part comme « burst » : sur un portable, le CPU tient un
turbo court (PL2) avant de redescendre à sa puissance soutenue (PL1). Il est affiché pour
information, mais n'entre jamais dans le score.

Le governor, le profil plateforme ACPI (`platform_profile`), l'EPP de cpu0
(`energy_performance_preference`), l'alimentation et la température CPU sont relevés avant et
après. hwbench avertit, sans bloquer, si la machine est sur batterie, si le profil d'énergie
n'est pas « performance », si le CPU dépasse 70 °C au départ (`--hot-start`) ou si les runs
varient de plus de 5 % (`--max-cv`).

Tant que le scoring (phase 3) n'existe pas, le score natif est un **indice brut** : la moyenne
géométrique de débits hétérogènes, sans unité, qui ne sert qu'à comparer deux résultats de la
même version du bench.

```
╭─ CPU single-core · native v1 ────────────────────────────────────────────────╮
│ Score (médiane)    126,0 indice brut  ± 0,8 (CV 0,6 %)                       │
│ Runs               125,0 · 126,0 · 126,6                                     │
│ Warm-up            2 itérations, 2,6 s · 6,3 s au total                      │
│ Burst (à froid)    125,1 indice brut  (hors score)                           │
│ Governor           performance                                               │
│ Profil plateforme  non disponible                                            │
│ EPP                performance                                               │
│ Alimentation       non disponible                                            │
│ Température CPU    41 °C avant → 62 °C après                                 │
│  Charge                                   Médiane                            │
│  SHA-256                             2368,3 Mio/s                            │
│  Compression zlib (niveau 6)           66,0 Mio/s                            │
│  Compression LZMA (preset 1)           23,6 Mio/s                            │
│  Exponentiation modulaire 2048 bits     69,0 op/s                            │
│ CPython 3.14.7 · OpenSSL 3.6.4 25 Aug 2026 · zlib 1.3.2 · liblzma 5.8.4      │
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
