"""Angel One WebSocket manager for live ticks."""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


class WebSocketManager:
    """Manages SmartAPI WebSocket for NIFTY, ATM CE, ATM PE live ticks."""

    def __init__(self) -> None:
        self._connected = False
        self._subscribed_tokens: list[str] = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self, feed_token: str) -> bool:
        logger.info("WebSocket connect requested — live integration pending")
        return False

    async def disconnect(self) -> None:
        self._connected = False
        self._subscribed_tokens.clear()
        logger.info("WebSocket disconnected")

    async def subscribe(self, tokens: list[str]) -> None:
        self._subscribed_tokens = tokens
        logger.info("WebSocket subscribe pending for tokens: %s", tokens)
