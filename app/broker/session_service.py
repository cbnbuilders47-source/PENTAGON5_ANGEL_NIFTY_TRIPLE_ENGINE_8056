"""Orchestrates Angel login, margin fetch, and WebSocket tick feed."""

from __future__ import annotations

from app.broker.angel_manager import AngelManager
from app.broker.margin_manager import MarginManager
from app.broker.token_manager import TokenManager
from app.broker.websocket_manager import WebSocketManager
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.state import AppState
from app.market.atm_manager import ATMManager
from app.market.candle_builder import CandleBuilder
from app.market.instrument_master import InstrumentMaster

logger = get_logger(__name__)


class BrokerSessionService:
    """Connect/disconnect lifecycle for broker + market data feed."""

    def __init__(
        self,
        settings: Settings,
        state: AppState,
        angel_manager: AngelManager,
        token_manager: TokenManager,
        margin_manager: MarginManager,
        websocket_manager: WebSocketManager,
        instrument_master: InstrumentMaster,
        atm_manager: ATMManager,
        candle_builder: CandleBuilder,
    ) -> None:
        self._settings = settings
        self._state = state
        self._angel = angel_manager
        self._tokens = token_manager
        self._margin = margin_manager
        self._ws = websocket_manager
        self._instruments = instrument_master
        self._atm = atm_manager
        self._candles = candle_builder

    async def connect(self) -> dict:
        if not self._settings.angel_configured:
            return {"success": False, "error": "Angel credentials not configured in .env"}

        if not await self._angel.connect():
            return {"success": False, "error": "Angel login failed"}

        self._state.broker_connected = True

        if not self._tokens.is_valid:
            return {"success": False, "error": "Token validation failed after login"}

        margin = await self._margin.refresh()
        if margin <= 0:
            logger.warning("Available margin is zero or unavailable")

        if not await self._instruments.load():
            return {"success": False, "error": "Failed to load instrument master"}

        nifty_ltp = self._angel.get_ltp(
            self._instruments.nifty_exchange,
            self._instruments.nifty_tradingsymbol,
            self._instruments.nifty_token,
        )
        if nifty_ltp is None:
            return {"success": False, "error": "Failed to fetch NIFTY LTP"}

        ce_token, pe_token = self._instruments.resolve_atm_options(nifty_ltp)
        if not ce_token or not pe_token:
            return {"success": False, "error": "Failed to resolve ATM CE/PE tokens"}

        self._atm.update(nifty_ltp, ce_token, pe_token)

        ws_ok = await self._ws.connect(
            jwt_token=self._tokens.jwt_token,
            feed_token=self._tokens.feed_token,
            client_code=self._settings.angel_client_code,
            api_key=self._settings.angel_api_key,
            subscriptions={
                "NIFTY": (self._instruments.nifty_exchange, self._instruments.nifty_token),
                "ATM_CE": ("NFO", ce_token),
                "ATM_PE": ("NFO", pe_token),
            },
            on_tick=self._handle_tick,
        )
        if not ws_ok:
            self._state.websocket_connected = False
            return {"success": False, "error": "WebSocket connection failed"}

        self._state.websocket_connected = True
        logger.info("Broker session connected — margin=%.2f", margin)
        return {
            "success": True,
            "available_margin": margin,
            "nifty_ltp": nifty_ltp,
            "atm_strike": self._atm.atm_strike,
        }

    async def disconnect(self) -> None:
        await self._ws.disconnect()
        await self._angel.disconnect()
        self._tokens.clear()
        self._state.broker_connected = False
        self._state.websocket_connected = False
        logger.info("Broker session disconnected")

    def _handle_tick(self, symbol: str, price: float, volume: int = 0) -> None:
        self._candles.on_tick(symbol, price, volume)

        if symbol != "NIFTY":
            return

        ce_token, pe_token = self._instruments.resolve_atm_options(price)
        if not ce_token or not pe_token:
            return
        if ce_token == self._atm.ce_token and pe_token == self._atm.pe_token:
            return

        self._atm.update(price, ce_token, pe_token)
        self._ws.update_option_subscriptions(
            {
                "ATM_CE": ("NFO", ce_token),
                "ATM_PE": ("NFO", pe_token),
            }
        )
