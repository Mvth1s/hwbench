# Fixture du rapport HTML

`session.json` : session de test du rapport (schéma d'export 3), rendue dans `session.html`
(snapshot de `tests/test_report.py`).

- **Réels** : résultats CPU et GPU, composants (snapshot), états machine et référence. Ils
  viennent de l'export du portable Dell (copie figée `tests/fixtures/exports/dell-latitude-5420-schema2.json`, identique au `results/dell-latitude-5420.json` de la 0.6.0), passé au schéma 3
  avec les réglages par défaut (`RunSettings()`).
- **Synthétiques** : les résultats mémoire (`native-memory-single`, `native-memory-multi`,
  `sysbench-memory-single`) et disque (`fio-disk`). Ce sont des valeurs construites pour couvrir
  ces sections ; seuls les 4 débits détaillés de `fio-disk` reprennent la sortie réelle de
  `tests/fixtures/tools/fio_disk.json`. Ils ne décrivent pas une mesure du Dell.
- Les scores ont été recalculés contre la référence du paquet au moment de la création ; le
  rapport les relit tels quels, sans dépendre de la référence actuelle.

Mettre à jour le snapshot après un changement voulu du gabarit :

```sh
HWBENCH_UPDATE_SNAPSHOTS=1 .venv/bin/pytest tests/test_report.py
```
