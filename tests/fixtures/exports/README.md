# Exports figés (schéma 2)

Copies des deux exports de `results/` tels qu'ils étaient à la release 0.6.0, avant leur
ré-export : `dell-latitude-5420-schema2.json` (portable Dell, Fedora) et
`asrock-b850-riptide-wifi-schema2.json` (desktop B850, machine de référence). Notés contre la
référence de la 0.5.0, sans mémoire ni disque, sans réglages enregistrés (`settings` absent).

Les tests qui ont besoin d'une vraie session (analyse, rapport, textes, relecture du schéma 2)
lisent ces copies, **jamais** `results/` : le contenu de `results/` change à chaque soumission
et à chaque ré-export (schéma, nombre de fichiers, référence). Seuls `tests/test_results_dir.py`
et le test du site réel (`test_real_site_has_no_ambiguous_plural`) lisent `results/`, parce
qu'ils valident justement ce qui s'y trouve. Ne jamais mettre ces copies à jour : ajouter un
nouveau fichier si un test a besoin d'un export plus récent.
