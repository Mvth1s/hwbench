"""Formatage des nombres pour l'affichage (français : virgule décimale). Jamais pour le JSON."""


def num(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def compact(value: float) -> str:
    """8.0 -> « 8 », 8.5 -> « 8,5 », 0.00048828125 -> « 0,000488281 »."""
    return f"{value:g}".replace(".", ",")
