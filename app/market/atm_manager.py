"""ATM CE/PE strike selection and token resolution."""

from __future__ import annotations

from app.core.logging import get_logger
from app.market.instrument_master import InstrumentMaster

logger = get_logger(__name__)


class ATMManager:
    """Resolves ATM CE and PE symbols/tokens for current NIFTY price."""

    def __init__(self, instrument_master: InstrumentMaster) -> None:
        self._master = instrument_master
        self._atm_strike: int | None = None
        self._ce_token: str | None = None
        self._pe_token: str | None = None

    @property
    def atm_strike(self) -> int | None:
        return self._atm_strike

    def update(self, nifty_ltp: float) -> int:
        self._atm_strike = self._master.get_atm_strike(nifty_ltp)
        return self._atm_strike
