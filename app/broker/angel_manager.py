"""Angel One SmartAPI session manager."""

from __future__ import annotations

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AngelManager:
    """Manages Angel One REST API session lifecycle."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connected = False
        self._session_token: str | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def session_token(self) -> str | None:
        return self._session_token

    async def connect(self) -> bool:
        """Authenticate via SmartAPI REST. Not implemented in milestone 1."""
        if not self._settings.angel_configured:
            logger.warning("Angel credentials not configured")
            return False
        logger.info("Angel connect requested — live integration pending")
        return False

    async def disconnect(self) -> None:
        self._connected = False
        self._session_token = None
        logger.info("Angel session disconnected")
