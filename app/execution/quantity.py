"""Lot quantity calculation from live margin."""

from __future__ import annotations

from app.core.constants import LOT_SIZE

MIN_PREMIUM = 20.0


def calculate_lots(
    allocated_margin: float,
    premium: float,
    available_margin: float,
    max_lots: int | None = None,
) -> tuple[int, int]:
    """Return (lots, quantity). Rounds down to valid lot count."""
    if premium <= 0 or allocated_margin <= 0:
        return 0, 0

    cost_per_lot = premium * LOT_SIZE
    if premium < MIN_PREMIUM:
        lots = int(allocated_margin // cost_per_lot)
    else:
        lots = int(allocated_margin // cost_per_lot)

    max_by_available = int(available_margin // cost_per_lot) if available_margin > 0 else lots
    lots = min(lots, max_by_available)

    if max_lots is not None:
        lots = min(lots, max_lots)

    lots = max(0, lots)
    return lots, lots * LOT_SIZE
