"""NIFTY options instrument master from Angel scrip master."""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


class InstrumentMaster:
    """Loads and caches NIFTY options instrument data."""

    def __init__(self) -> None:
        self._loaded = False

    async def load(self) -> None:
        logger.info("Instrument master load pending — live integration required")
        self._loaded = False

    def get_atm_strike(self, nifty_ltp: float) -> int:
        """Round NIFTY LTP to nearest 50 strike."""
        return int(round(nifty_ltp / 50) * 50)
