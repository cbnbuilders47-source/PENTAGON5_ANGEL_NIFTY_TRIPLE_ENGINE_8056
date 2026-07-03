"""Live position sync via Angel SmartAPI."""

from __future__ import annotations

import asyncio

from app.broker.angel_manager import AngelManager
from app.broker.rate_limit import RateLimitTracker
from app.core.logging import get_logger

logger = get_logger(__name__)


class PositionManager:
    def __init__(self, angel_manager: AngelManager, rate_limiter: RateLimitTracker) -> None:
        self._angel = angel_manager
        self._rate_limiter = rate_limiter
        self._positions: list[dict] = []

    async def get_positions(self) -> list[dict]:
        rows, _ = await self._fetch("position")
        return rows

    async def get_day_positions(self) -> list[dict]:
        rows, _ = await self._fetch("getPosition")
        return rows

    async def sync_positions(self) -> list[dict]:
        positions, _ = await self.sync_positions_with_status()
        return positions

    async def sync_positions_with_status(self) -> tuple[list[dict], bool]:
        """Return broker positions and whether the fetch succeeded (session connected)."""
        if not self._angel.smart_api or self._rate_limiter.is_limited:
            return [], False
        raw, raw_ok = await self._fetch("position")
        day, day_ok = await self._fetch("getPosition")
        merged = {str(p.get("symboltoken")): p for p in raw + day if p.get("symboltoken")}
        self._positions = list(merged.values())
        return self._positions, raw_ok or day_ok

    async def _fetch(self, method: str) -> tuple[list[dict], bool]:
        if not self._angel.smart_api or self._rate_limiter.is_limited:
            return [], False
        try:
            self._rate_limiter.record_call()
            response = await asyncio.to_thread(getattr(self._angel.smart_api, method))
            if response and response.get("status"):
                data = response.get("data", [])
                rows = data if isinstance(data, list) else []
                return rows, True
        except Exception as exc:
            logger.error("Position %s failed: %s", method, exc)
        return [], False
