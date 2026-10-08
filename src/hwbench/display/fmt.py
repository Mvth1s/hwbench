"""Formatage des nombres et des dates pour l'affichage (français). Jamais pour le JSON."""

from datetime import date


def num(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def compact(value: float) -> str:
    """8.0 -> « 8 », 8.5 -> « 8,5 », 0.00048828125 -> « 0,000488281 »."""
    return f"{value:g}".replace(".", ",")


def measure(value: float) -> str:
    """Valeur de bench : une décimale sous 10 000, aucune au-delà."""
    return num(value, 1 if value < 10_000 else 0)


def fr_date(iso: str | None) -> str | None:
    """« 2024-12-18 » ou « 2026-10-05T12:00:00+00:00 » -> « 18/12/2024 », « 05/10/2026 »."""
    if not iso:
        return None
    return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y")
