"""JWT and feed token management for Angel SmartAPI."""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


class TokenManager:
    """Caches and refreshes Angel auth tokens."""

    def __init__(self) -> None:
        self._jwt_token: str | None = None
        self._feed_token: str | None = None
        self._refresh_token: str | None = None

    @property
    def jwt_token(self) -> str | None:
        return self._jwt_token

    @property
    def feed_token(self) -> str | None:
        return self._feed_token

    def clear(self) -> None:
        self._jwt_token = None
        self._feed_token = None
        self._refresh_token = None
