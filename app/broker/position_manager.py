"""Position tracking via Angel SmartAPI."""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


class PositionManager:
    """Tracks open positions from Angel REST."""

    async def get_positions(self) -> list[dict]:
        return []

    async def get_day_positions(self) -> list[dict]:
        return []
