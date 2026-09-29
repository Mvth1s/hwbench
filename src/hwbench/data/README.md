# Données du paquet

`reference.json` : mesures de la machine de référence du scoring (1000 points). Ce fichier est
généré, jamais écrit à la main, sur la Dell Latitude 5420 en profil « performance », sur
secteur :

```sh
.venv/bin/hwbench reference -o src/hwbench/data/reference.json
```

La commande refuse d'écrire le fichier si la machine est sur batterie, si le profil d'énergie
n'est pas « performance » ou si un warm-up ne se stabilise pas (`--force` pour passer outre ;
le fichier le note alors dans `forced_reasons`). Tant qu'il n'existe pas, `hwbench bench`
affiche les valeurs brutes sans points.
