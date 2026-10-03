"""Formatage des nombres pour l'affichage (français : virgule décimale). Jamais pour le JSON."""


def num(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def compact(value: float) -> str:
    """8.0 -> « 8 », 8.5 -> « 8,5 », 0.00048828125 -> « 0,000488281 »."""
    return f"{value:g}".replace(".", ",")


def measure(value: float) -> str:
    """Valeur de bench : une décimale sous 10 000, aucune au-delà."""
    return num(value, 1 if value < 10_000 else 0)
