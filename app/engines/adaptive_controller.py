"""Adaptive controller — orchestrates Normal, Wick, and Ultra engines."""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.state import AppState
from app.engines.normal_engine import NormalEngine
from app.engines.ultra_engine import UltraEngine
from app.engines.wick_engine import WickEngine

logger = get_logger(__name__)


class AdaptiveController:
    """Coordinates engine lifecycle based on session phase and bias."""

    def __init__(self, state: AppState) -> None:
        self._state = state
        self.normal = NormalEngine()
        self.wick = WickEngine()
        self.ultra = UltraEngine()

    async def start_all(self) -> None:
        logger.info("Adaptive controller starting all engines")
        await self.normal.start()
        await self.wick.start()
        await self.ultra.start()

    async def stop_all(self) -> None:
        logger.info("Adaptive controller stopping all engines")
        await self.normal.stop()
        await self.wick.stop()
        await self.ultra.stop()
