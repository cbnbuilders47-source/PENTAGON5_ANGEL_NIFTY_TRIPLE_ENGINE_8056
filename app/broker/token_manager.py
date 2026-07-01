"""JWT and feed token management for Angel SmartAPI."""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


class TokenManager:
    """Caches and validates Angel auth tokens."""

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

    @property
    def refresh_token(self) -> str | None:
        return self._refresh_token

    @property
    def is_valid(self) -> bool:
        return bool(
            self._jwt_token
            and self._feed_token
            and len(self._jwt_token) > 20
            and len(self._feed_token) > 5
        )

    def set_tokens(
        self,
        jwt_token: str | None,
        feed_token: str | None,
        refresh_token: str | None = None,
    ) -> None:
        self._jwt_token = jwt_token
        self._feed_token = feed_token
        self._refresh_token = refresh_token
        if self.is_valid:
            logger.info("Angel tokens stored and validated")
        else:
            logger.warning("Angel tokens incomplete after set")

    def clear(self) -> None:
        self._jwt_token = None
        self._feed_token = None
        self._refresh_token = None
