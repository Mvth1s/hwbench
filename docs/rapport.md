# Rapport HTML déterministe (phase R)

> Statut : **en cours** (phase R). Remplace `idee.md`. L'export JSON (phase 4) et les catégories
> mémoire et disque (phase C) sont faits ; le rapport et la page machine du classement partagent
> désormais un même moteur de rendu.

## 1. Objectif

Produire, à la demande, un rapport d'analyse HTML autonome à partir d'une session de benchmarks :
lisible par n'importe qui, avec le détail technique pour ceux qui le veulent.

Aujourd'hui, comprendre les résultats demande de connaître le CV, l'EPP, le burst, etc. Le
rapport est produit par hwbench lui-même, de façon **déterministe et reproductible** : mêmes
données, même HTML, à l'octet près.

La page de chaque machine du classement en ligne réutilise les mêmes sections (mêmes graphiques,
même synthèse), sans les recommandations.

## 2. Comportement

**Pas activé par défaut** : aucun fichier n'est écrit sans le demander.

```
$ hwbench bench --report
… (affichage rich actuel, inchangé)

Rapport enregistré :
  JSON  ~/.local/share/hwbench/reports/2026-10-09_153012.json
  HTML  ~/.local/share/hwbench/reports/2026-10-09_153012.html
```

| Commande | Effet |
|---|---|
| `hwbench bench …` / `hwbench export -o F …` | comportement actuel, aucun rapport |
| `hwbench bench --report` / `hwbench export -o F --report` | JSON + HTML dans le dossier des rapports |
| `--report-dir DIR` (avec `--report`) | autre dossier |
| `hwbench report FICHIER.json [-o rapport.html]` | HTML depuis un JSON existant (session ou export, y compris un fichier de `results/`) ; défaut : même nom, extension `.html` |

- `--report` et `hwbench report` passent par **la même fonction** (`report.render_report`).
- Dossier par défaut : `$XDG_DATA_HOME/hwbench/reports/`, soit `~/.local/share/hwbench/reports/`.
- Nom des fichiers : **horodatage seul** (`AAAA-MM-JJ_HHMMSS`, heure locale), sans modèle de
  machine ni hostname.
- Bench interrompu (Ctrl+C) ou sans aucun résultat (code 1) : **aucun fichier**.
- Bench partiel (`hwbench bench cpu-single --report`) : seules les sections mesurées sont
  présentes ; les autres sont absentes, pas vides.
- Sans référence : scores bruts, avec le bandeau « scores non normalisés » (`NO_REFERENCE`).

## 3. Données

Le **JSON est la seule source du HTML**. Le rendu ne lit que le JSON relu en dataclasses
(`export.from_dict`), jamais le système : `hwbench report` sur le JSON d'une session donne
exactement le HTML écrit en fin de bench (testé : session → JSON → HTML identique).

La session est un `MachineExport` (même schéma que `hwbench export`) :

| Donnée | Source |
|---|---|
| Résultats | `list[Result]` : médiane, stdev, runs, burst, warm-up, détails, état avant/après, avertissements |
| Scores | `Scores` (backends, catégories, combiné), si une référence existe |
| Composants | `MachineSnapshot` : `bench --report` le collecte (`collect_snapshot()`, sans identifiant), comme `export` |
| Réglages | `RunSettings` réellement appliqués (CV, départ chaud, tolérance et plafond de warm-up) : **à ajouter à l'export** (schéma 3, champ `settings`). Un export de schéma 2 (fichiers actuels de `results/`) reste lisible : le rapport utilise alors les réglages par défaut et l'indique |
| Méta | version de hwbench, date ISO, modèle de machine |

`privacy.scrub()` est appliqué au JSON avant écriture, et au JSON embarqué dans le HTML.

## 4. Ton et rédaction

Le lecteur visé est un **adulte non technicien**, sans infantiliser.

- Pas de métaphores, pas d'emojis.
- Phrases courtes, à l'indicatif. Exemple : « Les tests ont été réalisés sur batterie en mode
  équilibré. »
- Les termes techniques sont gardés tels quels (CPU, EPP, CV, fps, IOPS) et **expliqués une
  fois** : infobulle `<abbr title>` et lexique en fin de rapport.
- États nommés avec un vocabulaire neutre et constant : **Fiable · À vérifier · À corriger**.
- **Aucune hypothèse non mesurée.** Le rapport constate et cite les seuils : il n'explique pas
  une cause qu'il n'a pas mesurée (pas de « probablement à cause du cache L3 »).
- **Seuils lus dans les `RunSettings`** de la session, jamais de constantes dupliquées.
- Français, nombres via `display/fmt.py` (virgule décimale). Libellés fabricant jamais
  reformatés.

## 5. Structure du HTML

1. **En-tête** : machine, CPU, GPU, date, version de hwbench, durée de la session.
2. **Chiffres clés** (3 à 5 tuiles) : score combiné si une référence existe (sinon CPU single,
   CPU multi et GPU en valeurs brutes), et une tuile « Conditions » (Fiable · À vérifier · À
   corriger).
3. **Synthèse** : 3 à 5 phrases issues des règles (§ 6), de la plus importante à la moins
   importante.
4. **Conditions de mesure** : alimentation, profil plateforme, EPP, governor (affiché, jamais
   jugé), température de départ ; un statut et une phrase par ligne.
5. **Processeur** : tableau single / multi par backend, facteur multi / single et nombre de
   processus ; détail des charges natives en barres horizontales.
6. **Carte graphique** : un bloc par outil (score, résolution, mode de présentation, pilote) ;
   mention fixe « les scores de deux outils différents ne se comparent pas entre eux ».
7. **Mémoire** (catégorie d'information, hors score combiné) : copie native single et
   multi-processus, sysbench memory ; facteur multi / single.
8. **Disque** (catégorie d'information, hors score combiné) : les 4 tests fio en barres (Mio/s et
   IOPS séparés), taille du fichier, système de fichiers et modèle du disque, avec une note
   fixe : le score disque dépend du système de fichiers (btrfs, ext4…) et du cache des SSD ; il
   ne se compare qu'à configuration et taille de fichier égales.
9. **Températures** : frise de la session (un segment par test, largeur = durée, température
   avant puis après, seuil du capteur CPU s'il est connu) ; capteurs au repos du snapshot.
10. **Fiabilité des mesures** : CV par test avec statut, runs, burst comparé à la médiane,
    warm-up stable ou non.
11. **Composants** : le contenu de `hwbench info`, avec « non disponible » ou « relancer avec
    sudo ».
12. **Recommandations** (rapport seulement, absent de la page du classement) : actions issues des
    règles, avec les commandes exactes (`powerprofilesctl set performance`, `sudo hwbench info`).
13. **Lexique** : uniquement les termes présents dans le rapport.
14. **Annexe** : tableau brut de tous les résultats et JSON embarqué
    (`<script type="application/json">`), pour qu'un HTML seul suffise à retrouver les données.

### Contraintes visuelles

- **Fichier unique, 100 % hors ligne** : CSS et SVG intégrés, aucune police, aucun script, aucun
  CDN, aucune URL `http(s)` dans `src` ou `href`, pas d'`@import`. Police système.
- Graphiques en **SVG générés en Python** (barres horizontales, frise thermique), sans
  bibliothèque. Chaque graphique est accompagné de ses valeurs en texte ou en tableau.
- Thème clair et sombre (`prefers-color-scheme`), lisible sur mobile, **imprimable**
  (`@media print`).
- Couleurs réservées aux statuts et à une seule couleur de données.

## 6. Moteur de règles (`analysis.py`)

Chaque phrase de la synthèse et chaque recommandation vient d'une règle. Une règle se déclenche
sur les données et produit un `Finding` : un **code**, un statut et des paramètres (comme
`BenchWarning`), traduits en texte dans la couche de rendu. `analysis.py` ne dépend que des
modèles (`results`, `models`, `scoring`, `export`, `runner.RunSettings`) : testable sans HTML,
règle par règle, y compris l'absence de faux positifs.

| Règle | Condition | Statut |
|---|---|---|
| Sur batterie | `ON_BATTERY` sur au moins un test | À corriger |
| Profil non performance | `POWER_PROFILE` : **EPP ou profil plateforme** (`MachineState.throttling_settings`), jamais le governor (sous `intel_pstate`, « powersave » est le governor normal) | À corriger |
| Rendu logiciel | `SOFTWARE_RENDERING` | À corriger |
| Départ chaud | `HOT_START` (température, seuil `hot_start_c`, test précédent) | À vérifier |
| Mesure instable | `HIGH_VARIANCE` (CV, seuil `high_variance_cv_percent`) | À vérifier |
| Warm-up instable | `WARMUP_UNSTABLE` (plafond de la catégorie) | À vérifier |
| Vsync non vérifiée | `VSYNC_UNVERIFIED` | À vérifier |
| Mesures reproductibles | tous les CV ≤ `reliable_cv_percent` (1 %, ajouté à `RunSettings`) | Fiable |
| Températures | maximum relevé sous le seuil haut du capteur CPU (s'il est connu) | Fiable |
| Facteur multi-cœur | multi / single, CPU et mémoire, par backend | info |
| Données incomplètes | `Unavailable.NEEDS_ROOT` dans le snapshot | info |
| Pas de référence | export sans référence | info |
| Catégorie hors référence | mémoire ou disque sans points (`NOT_IN_REFERENCE`) | info |
| Score disque | bench disque présent : système de fichiers, taille, modèle | info |

Principes :
- Ordre de la synthèse : À corriger > À vérifier > Fiable > info.
- Le rapport ne juge pas une machine « bonne » ou « mauvaise » : sans référence il décrit, avec
  une référence il compare aux 1000 points.

## 7. Architecture

```
src/hwbench/
├── export.py            # session -> JSON versionné (schéma 3 : + settings), et l'inverse
├── analysis.py          # moteur de règles : session -> list[Finding] (codes + paramètres)
└── report/
    ├── __init__.py      # render_report(session) -> str (HTML), seule fonction d'entrée
    ├── html.py          # moteur commun : CSS, échappement, en-tête, page (repris du classement)
    ├── texts.py         # traductions FR des codes Finding, lexique
    ├── charts.py        # SVG : barres horizontales, frise thermique
    └── sections.py      # sections, partagées avec leaderboard/site.py (page machine)
```

- `report/` consomme la session et les `Finding`, et n'interroge jamais le système.
- Pas de nouvelle dépendance : f-strings et `html.escape`.
- `leaderboard/site.py` garde son index et son fonctionnement ; la page machine assemble les
  sections du rapport sans les recommandations.

## 8. Tests

- **Analyse** : une session construite à la main par règle → le bon `Finding`, et aucun faux
  positif.
- **Rendu** : HTML généré depuis une session de fixture et comparé à un fichier de référence
  (snapshot), mis à jour volontairement.
- **Hors ligne** : aucun `http://` ni `https://` dans `src=` ou `href=`, pas d'`@import`.
- **Vie privée** : aucun identifiant (fixtures `FAKE…`, système de test) dans le JSON ni le HTML.
- **Aller-retour** : session → JSON → session → HTML identique au HTML direct.
- **CLI** : sans `--report` rien n'est écrit ; un bench sans résultat n'écrit rien ;
  `hwbench report` sur un schéma inconnu → erreur explicite.
- **Réel** : rapport et site générés depuis les deux fichiers de `results/`.
