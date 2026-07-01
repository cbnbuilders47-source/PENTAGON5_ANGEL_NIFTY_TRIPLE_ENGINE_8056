"""Ultra Engine — 40% default capital allocation."""

from __future__ import annotations

from app.core.logging import get_logger
from app.models.enums import EngineStatus

logger = get_logger(__name__)


class UltraEngine:
    """High-conviction NIFTY options trading engine."""

    NAME = "ultra"

    def __init__(self) -> None:
        self.status = EngineStatus.IDLE

    async def start(self) -> None:
        logger.info("Ultra Engine start requested")
        self.status = EngineStatus.ANALYZING

    async def stop(self) -> None:
        logger.info("Ultra Engine stopped")
        self.status = EngineStatus.STOPPED
