"""Order placement and management — LIVE ONLY."""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


class OrderManager:
    """Handles order placement via Angel SmartAPI REST. Not active in milestone 1."""

    async def place_order(self, **kwargs) -> dict:
        raise NotImplementedError("Live order placement not enabled in milestone 1")

    async def cancel_order(self, order_id: str) -> dict:
        raise NotImplementedError("Live order cancellation not enabled in milestone 1")

    async def get_order_book(self) -> list[dict]:
        return []

    async def get_trade_book(self) -> list[dict]:
        return []
