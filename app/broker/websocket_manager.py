"""Angel One WebSocket manager for live ticks."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

from app.core.logging import get_logger

logger = get_logger(__name__)

# SmartAPI WebSocket V2 exchange types
_EXCHANGE_MAP = {
    "NSE": 1,
    "NFO": 2,
    "BSE": 3,
    "BFO": 4,
    "MCX": 5,
    "NCX": 7,
    "CDS": 13,
}

_WS_MODE_LTP = 1


class WebSocketManager:
    """Manages SmartAPI WebSocket V2 for NIFTY, ATM CE, ATM PE live ticks."""

    def __init__(self) -> None:
        self._connected = False
        self._ws = None
        self._thread: threading.Thread | None = None
        self._token_to_symbol: dict[str, str] = {}
        self._subscriptions: dict[str, tuple[str, str]] = {}
        self._on_tick: Callable[[str, float, int], None] | None = None
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(
        self,
        jwt_token: str,
        feed_token: str,
        client_code: str,
        api_key: str,
        subscriptions: dict[str, tuple[str, str]],
        on_tick: Callable[[str, float, int], None],
    ) -> bool:
        await self.disconnect()

        self._on_tick = on_tick
        self._subscriptions = dict(subscriptions)
        self._token_to_symbol = {token: symbol for symbol, (_, token) in subscriptions.items()}

        try:
            await asyncio.to_thread(
                self._start_ws_thread,
                jwt_token,
                feed_token,
                client_code,
                api_key,
                subscriptions,
            )
        except Exception as exc:
            logger.exception("WebSocket connect failed: %s", exc)
            return False

        self._connected = True
        return True

    def _start_ws_thread(
        self,
        jwt_token: str,
        feed_token: str,
        client_code: str,
        api_key: str,
        subscriptions: dict[str, tuple[str, str]],
    ) -> None:
        from SmartApi.smartWebSocketV2 import SmartWebSocketV2

        token_list = self._build_token_list(subscriptions)
        correlation_id = str(uuid.uuid4())

        sws = SmartWebSocketV2(jwt_token, api_key, client_code, feed_token)
        self._ws = sws

        def on_data(_wsapp, message: dict) -> None:
            self._process_tick(message)

        def on_open(_wsapp) -> None:
            logger.info("WebSocket open — subscribing to %s", list(subscriptions.keys()))
            sws.subscribe(correlation_id, _WS_MODE_LTP, token_list)

        def on_error(_wsapp, error) -> None:
            logger.error("WebSocket error: %s", error)

        def on_close(_wsapp, *_args) -> None:
            logger.info("WebSocket closed")
            self._connected = False

        sws.on_open = on_open
        sws.on_data = on_data
        sws.on_error = on_error
        sws.on_close = on_close

        self._thread = threading.Thread(target=sws.connect, daemon=True, name="angel-ws")
        self._thread.start()

    def _build_token_list(self, subscriptions: dict[str, tuple[str, str]]) -> list[dict]:
        by_exchange: dict[int, list[str]] = {}
        for _symbol, (exchange, token) in subscriptions.items():
            exch_type = _EXCHANGE_MAP.get(exchange.upper())
            if exch_type is None:
                continue
            by_exchange.setdefault(exch_type, []).append(str(token))

        return [
            {"exchangeType": exch_type, "tokens": tokens}
            for exch_type, tokens in by_exchange.items()
        ]

    def _process_tick(self, message: dict) -> None:
        if not isinstance(message, dict):
            return

        token = str(message.get("token", ""))
        symbol = self._token_to_symbol.get(token)
        if not symbol:
            return

        ltp_raw = message.get("last_traded_price")
        if ltp_raw is None:
            return

        price = float(ltp_raw) / 100.0
        volume = int(message.get("last_traded_quantity") or message.get("volume_trade_for_the_day") or 0)

        if self._on_tick:
            self._on_tick(symbol, price, volume)

    def update_option_subscriptions(self, options: dict[str, tuple[str, str]]) -> None:
        """Resubscribe when ATM strike rolls to new CE/PE tokens."""
        with self._lock:
            for symbol, (exchange, token) in options.items():
                old_token = self._subscriptions.get(symbol, (None, None))[1]
                if old_token and old_token in self._token_to_symbol:
                    del self._token_to_symbol[old_token]
                self._subscriptions[symbol] = (exchange, token)
                self._token_to_symbol[str(token)] = symbol

        if not self._ws or not self._connected:
            return

        token_list = self._build_token_list(options)
        correlation_id = str(uuid.uuid4())
        try:
            self._ws.subscribe(correlation_id, _WS_MODE_LTP, token_list)
            logger.info("WebSocket resubscribed ATM options: %s", list(options.keys()))
        except Exception as exc:
            logger.error("ATM resubscribe failed: %s", exc)

    async def disconnect(self) -> None:
        if self._ws:
            try:
                await asyncio.to_thread(self._ws.close_connection)
            except Exception as exc:
                logger.warning("WebSocket close error: %s", exc)

        self._ws = None
        self._thread = None
        self._connected = False
        self._token_to_symbol.clear()
        self._subscriptions.clear()
        self._on_tick = None
        logger.info("WebSocket disconnected")
