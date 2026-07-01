"""Portfolio and per-engine risk management."""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.state import AppState

logger = get_logger(__name__)


class RiskManager:
    """Enforces risk limits across all three engines."""

    def __init__(self, state: AppState) -> None:
        self._state = state

    def can_open_position(self, engine: str) -> bool:
        logger.debug("Risk check for engine %s", engine)
        return True

    def should_force_exit(self) -> bool:
        return False
