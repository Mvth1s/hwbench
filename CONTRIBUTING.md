# Contribuer

## Soumettre un résultat au classement

Le classement (site GitHub Pages du dépôt) est généré à partir des fichiers de `results/`.
Chaque machine y entre par une pull request qui ajoute **un** fichier `results/<nom>.json`.

**Licence des résultats : CC0-1.0.** Un fichier de `results/` est une donnée (mesures et
description du matériel), pas du code : il est publié sous
[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/deed.fr) (domaine public, réutilisable
sans condition), et non sous la licence AGPL du logiciel. En ouvrant la pull request, vous
acceptez de publier votre fichier sous CC0-1.0.

1. **Installer la dernière version** de hwbench : la validation exige un export noté contre la
   référence actuelle et des benchs à leur version courante.

   ```sh
   pipx install hwbench        # ou : pipx upgrade hwbench
   ```

2. **Mesurer dans de bonnes conditions** : sur secteur, profil d'énergie « performance »,
   machine au repos (navigateur et autres programmes fermés), depuis la session graphique pour
   les benchs GPU. Installer sysbench, glmark2 et vkmark si possible : le score GPU, et donc le
   score combiné, ne sont classés qu'avec les mêmes backends que la machine de référence.

3. **Exporter** dans un clone de votre fork du dépôt :

   ```sh
   hwbench export -o results/<nom>.json
   ```

   `<nom>` : minuscules, chiffres et tirets (`mon-desktop`, `latitude-5420`). Il apparaît
   publiquement dans l'adresse de la page de la machine : n'y mettez pas votre nom si vous ne
   souhaitez pas qu'il soit publié.

4. **Vérifier** avant d'envoyer (depuis le clone, avec hwbench installé en mode développement
   via `pip install -e .`) :

   ```sh
   python -m hwbench.leaderboard validate results/<nom>.json
   ```

5. **Ouvrir la pull request** vers la branche `dev`, avec un message de commit conventionnel
   (vérifié par commitlint), par exemple :

   ```
   chore(results): add mon-desktop
   ```

La CI valide le fichier : schéma d'export connu, aucun identifiant, référence actuelle et non
forcée, versions de bench à jour, points cohérents avec les résultats bruts. Un message clair
indique chaque problème. Une fois la pull request fusionnée, la machine apparaît sur le site à
la release suivante (fusion de `dev` dans `main`).

## Ce qui est publié

Le fichier soumis est publié tel quel dans le dépôt, et ses données sur le site :

- les **composants, sans aucun identifiant** : modèles de CPU, GPU, carte mère, disques,
  quantité et type de RAM, relevés de capteurs. Numéros de série, UUID, adresses MAC, hostname
  et asset tags ne sont jamais collectés dans un export, et la validation refuse tout fichier
  qui en contiendrait ;
- les **résultats** : valeurs brutes de chaque run, médiane, écart-type, versions des outils et
  du pilote GPU, conditions de mesure (governor, profil d'énergie, alimentation, températures) ;
- la version de hwbench et la date de l'export.

Les points affichés sont recalculés par le site à partir des résultats bruts, contre la
référence du paquet.

## Résultats déclaratifs

Les résultats sont **déclaratifs** : la validation vérifie la forme, la cohérence et l'absence
d'identifiants, pas l'honnêteté de la mesure. Rien ne garantit qu'un résultat n'a pas été
obtenu sur une machine modifiée ou retouché avant l'export. Les mainteneurs peuvent refuser ou
retirer un résultat manifestement aberrant.

## Données personnelles (RGPD)

Le **pseudonyme GitHub de l'auteur de la pull request** est une donnée personnelle : il reste
visible dans la pull request et dans l'historique git du dépôt, et le `<nom>` choisi apparaît
sur le site.

Vous pouvez demander la **suppression de votre résultat sur simple demande**, en ouvrant une
issue ou une pull request de retrait (qui supprime `results/<nom>.json`). Le fichier est alors
retiré du dépôt et du site au déploiement suivant. Pour une demande d'effacement allant au-delà
(historique git, pages de pull request), précisez-le dans l'issue : elle est traitée au cas par
cas.

## Contribuer au code

Le code de hwbench est sous licence AGPL-3.0-or-later : une contribution de code est acceptée
sous cette même licence. Développement sur `dev`, pull requests vers `dev`, messages de commit
conventionnels. Avant
d'ouvrir une pull request, `scripts/ci-local.sh` reproduit la CI (venv neuf, ruff, pytest,
commitlint). Voir aussi le README pour l'installation de développement.
