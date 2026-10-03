// Conventional commits, vérifiés sur les PR par .github/workflows/commitlint.yml.
export default {
  extends: ["@commitlint/config-conventional"],
  rules: {
    // corps de commit libres (listes, chemins, sorties d'outils) : pas de limite de ligne
    "body-max-line-length": [0],
    "footer-max-line-length": [0],
  },
};
