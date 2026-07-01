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
        return await self._fetch("position")

    async def get_day_positions(self) -> list[dict]:
        return await self._fetch("getPosition")

    async def sync_positions(self) -> list[dict]:
        raw = await self.get_positions()
        day = await self.get_day_positions()
        merged = {str(p.get("symboltoken")): p for p in raw + day if p.get("symboltoken")}
        self._positions = list(merged.values())
        return self._positions

    async def _fetch(self, method: str) -> list[dict]:
        if not self._angel.smart_api or self._rate_limiter.is_limited:
            return []
        try:
            self._rate_limiter.record_call()
            response = await asyncio.to_thread(getattr(self._angel.smart_api, method))
            if response and response.get("status"):
                data = response.get("data", [])
                return data if isinstance(data, list) else []
        except Exception as exc:
            logger.error("Position %s failed: %s", method, exc)
        return []
