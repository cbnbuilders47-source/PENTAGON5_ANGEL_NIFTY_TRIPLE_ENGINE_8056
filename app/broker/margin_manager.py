"""Available margin management — auto-fetched from Angel after login."""

from __future__ import annotations

import asyncio

from app.broker.angel_manager import AngelManager
from app.core.logging import get_logger
from app.core.state import AppState

logger = get_logger(__name__)


class MarginManager:
    """Fetches and tracks available margin from Angel One RMS API."""

    def __init__(self, state: AppState, angel_manager: AngelManager) -> None:
        self._state = state
        self._angel = angel_manager

    async def refresh(self) -> float:
        if not self._angel.is_connected or not self._angel.smart_api:
            logger.debug("Margin refresh skipped — broker not connected")
            return self._state.available_margin

        try:
            margin = await asyncio.to_thread(self._fetch_margin_sync)
        except Exception as exc:
            logger.exception("Margin fetch failed: %s", exc)
            return self._state.available_margin

        self._state.set_available_margin(margin)
        logger.info("Available margin updated: %.2f", margin)
        return margin

    def _fetch_margin_sync(self) -> float:
        response = self._angel.smart_api.rmsLimit()
        if not response or not response.get("status"):
            message = response.get("message", "unknown") if response else "empty"
            raise RuntimeError(f"rmsLimit failed: {message}")

        data = response.get("data", {})
        for key in ("availablecash", "net"):
            if key in data and data[key] is not None:
                return float(data[key])

        raise RuntimeError("rmsLimit response missing availablecash/net")
