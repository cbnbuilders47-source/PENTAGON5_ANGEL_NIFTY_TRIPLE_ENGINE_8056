"""Angel One SmartAPI session manager."""

from __future__ import annotations

import asyncio

from app.broker.token_manager import TokenManager
from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AngelManager:
    """Manages Angel One REST API session lifecycle."""

    def __init__(self, settings: Settings, token_manager: TokenManager) -> None:
        self._settings = settings
        self._tokens = token_manager
        self._connected = False
        self._smart_api = None

    @property
    def is_connected(self) -> bool:
        return self._connected and self._tokens.is_valid

    @property
    def smart_api(self):
        return self._smart_api

    async def connect(self) -> bool:
        if not self._settings.angel_configured:
            logger.warning("Angel credentials not configured")
            return False

        try:
            result = await asyncio.to_thread(self._login_sync)
        except Exception as exc:
            logger.exception("Angel login failed: %s", exc)
            return False

        if not result:
            return False

        self._connected = True
        logger.info("Angel SmartAPI session established")
        return True

    def _login_sync(self) -> bool:
        import pyotp
        from SmartApi import SmartConnect

        totp = pyotp.TOTP(self._settings.angel_totp_secret).now()
        smart_api = SmartConnect(api_key=self._settings.angel_api_key)
        session = smart_api.generateSession(
            self._settings.angel_client_code,
            self._settings.angel_password,
            totp,
        )

        if not session or not session.get("status"):
            message = session.get("message", "unknown error") if session else "empty response"
            logger.error("Angel generateSession failed: %s", message)
            return False

        data = session.get("data", {})
        jwt_token = data.get("jwtToken")
        refresh_token = data.get("refreshToken")
        if not jwt_token:
            logger.error("Angel login missing jwtToken")
            return False

        feed_token = smart_api.getfeedToken()
        self._smart_api = smart_api
        self._tokens.set_tokens(jwt_token, feed_token, refresh_token)
        return self._tokens.is_valid

    def get_ltp(self, exchange: str, tradingsymbol: str, symboltoken: str) -> float | None:
        if not self._smart_api:
            return None
        try:
            response = self._smart_api.ltpData(exchange, tradingsymbol, symboltoken)
        except Exception as exc:
            logger.error("LTP fetch failed for %s: %s", tradingsymbol, exc)
            return None

        if not response or not response.get("status"):
            logger.error("LTP response error for %s: %s", tradingsymbol, response)
            return None

        data = response.get("data", {})
        ltp_raw = data.get("ltp")
        if ltp_raw is None:
            return None
        return float(ltp_raw)

    async def disconnect(self) -> None:
        if self._smart_api and self._connected:
            try:
                await asyncio.to_thread(self._smart_api.terminateSession, self._settings.angel_client_code)
            except Exception as exc:
                logger.warning("Angel terminateSession failed: %s", exc)

        self._connected = False
        self._smart_api = None
        self._tokens.clear()
        logger.info("Angel session disconnected")
