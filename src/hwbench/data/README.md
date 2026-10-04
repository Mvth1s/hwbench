# Données du paquet

`reference.json` : mesures de la machine de référence du scoring (1000 points). Ce fichier est
généré, jamais écrit à la main, sur le desktop ASRock B850 (Ryzen 7 8700F, RX 9070 XT,
EndeavourOS), depuis la session graphique et sans autre charge :

```sh
.venv/bin/hwbench reference -o src/hwbench/data/reference.json
```

À régénérer seulement quand la version d'un bench est incrémentée (`tests/test_reference_file.py`
échoue alors) ou quand sysbench, glmark2 ou vkmark changent de version sur le desktop. Une mise
à jour du pilote GPU (Mesa) ne l'impose pas : le pilote est une information. `hwbench bench`
avertit seulement quand le GPU mesuré est celui de la référence et que la version amont du
pilote diffère (la révision du paquet, `-arch1.1` ou absente sous Fedora, est ignorée).

La commande refuse d'écrire le fichier si la machine est sur batterie, si le profil d'énergie
n'est pas « performance » ou si un warm-up ne se stabilise pas (`--force` pour passer outre ;
le fichier le note alors dans `forced_reasons`). Tant qu'il n'existe pas, `hwbench bench`
affiche les valeurs brutes sans points.
