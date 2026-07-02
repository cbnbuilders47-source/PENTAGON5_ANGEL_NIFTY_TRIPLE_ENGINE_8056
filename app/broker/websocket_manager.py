"""Angel One WebSocket manager for live ticks."""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime

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
_BASE_BACKOFF_SEC = 3
_MAX_BACKOFF_SEC = 60
_MAX_RECONNECT_ATTEMPTS = 12


class WebSocketManager:
    """Manages SmartAPI WebSocket V2 for NIFTY, ATM CE, ATM PE live ticks."""

    def __init__(self) -> None:
        self._connected = False
        self._ws = None
        self._thread: threading.Thread | None = None
        self._token_to_symbol: dict[str, str] = {}
        self._subscriptions: dict[str, tuple[str, str]] = {}
        self._on_tick: Callable[[str, float, int], None] | None = None
        self._on_status_change: Callable[[bool], None] | None = None
        self._on_reconnect_status: Callable[[dict], None] | None = None
        self._lock = threading.Lock()
        self._last_tick_at: dict[str, datetime] = {}
        self._stale_threshold_sec = 30
        self._reconnect_creds: dict | None = None
        self._reconnect_attempt = 0
        self._reconnecting = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def reconnect_attempt(self) -> int:
        return self._reconnect_attempt

    async def connect(
        self,
        jwt_token: str,
        feed_token: str,
        client_code: str,
        api_key: str,
        subscriptions: dict[str, tuple[str, str]],
        on_tick: Callable[[str, float, int], None],
        on_status_change: Callable[[bool], None] | None = None,
        on_reconnect_status: Callable[[dict], None] | None = None,
    ) -> bool:
        await self.disconnect()

        self._on_tick = on_tick
        self._on_status_change = on_status_change
        self._on_reconnect_status = on_reconnect_status
        self._subscriptions = dict(subscriptions)
        self._token_to_symbol = {token: symbol for symbol, (_, token) in subscriptions.items()}
        self._reconnect_creds = {
            "jwt_token": jwt_token,
            "feed_token": feed_token,
            "client_code": client_code,
            "api_key": api_key,
            "subscriptions": dict(subscriptions),
        }
        self._reconnect_attempt = 0

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
        if self._on_status_change:
            self._on_status_change(True)
        return True

    def _stop_ws_connection(self) -> None:
        """Close existing socket before starting a replacement thread."""
        with self._lock:
            ws = self._ws
            self._ws = None
            self._thread = None
            self._connected = False
        if ws:
            try:
                ws.close_connection()
            except Exception as exc:
                logger.warning("WebSocket close before reconnect: %s", exc)

    def _start_ws_thread(
        self,
        jwt_token: str,
        feed_token: str,
        client_code: str,
        api_key: str,
        subscriptions: dict[str, tuple[str, str]],
    ) -> None:
        self._stop_ws_connection()
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
            self._connected = True
            self._reconnect_attempt = 0
            self._reconnecting = False
            self._emit_reconnect_status("connected", "WebSocket connected")
            if self._on_status_change:
                self._on_status_change(True)

        def on_error(_wsapp, error) -> None:
            logger.error("WebSocket error: %s", error)

        def on_close(_wsapp, *_args) -> None:
            logger.info("WebSocket closed — scheduling reconnect")
            self._connected = False
            if self._on_status_change:
                self._on_status_change(False)
            self._schedule_reconnect()

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
        self._last_tick_at[symbol] = datetime.now()

        if self._on_tick:
            self._on_tick(symbol, price, volume)

    def get_last_tick_at(self, symbol: str) -> datetime | None:
        return self._last_tick_at.get(symbol)

    def is_stale(self, symbol: str) -> bool:
        last = self._last_tick_at.get(symbol)
        if not last:
            return True
        return (datetime.now() - last).total_seconds() > self._stale_threshold_sec

    def _emit_reconnect_status(self, status: str, message: str) -> None:
        payload = {
            "status": status,
            "message": message,
            "attempt": self._reconnect_attempt,
            "at": datetime.now().isoformat(),
        }
        if self._on_reconnect_status:
            self._on_reconnect_status(payload)

    def _schedule_reconnect(self) -> None:
        if not self._reconnect_creds or self._reconnecting:
            return
        if self._reconnect_attempt >= _MAX_RECONNECT_ATTEMPTS:
            logger.error("WebSocket reconnect exhausted after %d attempts", self._reconnect_attempt)
            self._emit_reconnect_status("failed", "Reconnect attempts exhausted")
            return

        creds = self._reconnect_creds
        self._reconnecting = True
        self._reconnect_attempt += 1
        delay = min(_MAX_BACKOFF_SEC, _BASE_BACKOFF_SEC * (2 ** (self._reconnect_attempt - 1)))
        logger.info("WebSocket reconnect attempt %d in %.1fs", self._reconnect_attempt, delay)
        self._emit_reconnect_status("retrying", f"Reconnect attempt {self._reconnect_attempt} in {delay:.0f}s")

        def _reconnect() -> None:
            time.sleep(delay)
            self._reconnecting = False
            if self._connected:
                return
            try:
                self._start_ws_thread(
                    creds["jwt_token"],
                    creds["feed_token"],
                    creds["client_code"],
                    creds["api_key"],
                    creds["subscriptions"],
                )
            except Exception as exc:
                logger.error("WebSocket reconnect failed: %s", exc)
                self._emit_reconnect_status("error", str(exc))
                if self._on_status_change:
                    self._on_status_change(False)
                self._schedule_reconnect()

        threading.Thread(target=_reconnect, daemon=True, name="ws-reconnect").start()

    def update_option_subscriptions(self, options: dict[str, tuple[str, str]]) -> None:
        """Resubscribe when ATM strike rolls to new CE/PE tokens."""
        with self._lock:
            for symbol, (exchange, token) in options.items():
                old_token = self._subscriptions.get(symbol, (None, None))[1]
                if old_token and old_token in self._token_to_symbol:
                    del self._token_to_symbol[old_token]
                self._subscriptions[symbol] = (exchange, token)
                self._token_to_symbol[str(token)] = symbol
            if self._reconnect_creds:
                merged = dict(self._reconnect_creds.get("subscriptions", {}))
                merged.update(options)
                self._reconnect_creds["subscriptions"] = merged

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
        self._reconnect_creds = None
        self._reconnect_attempt = 0
        self._reconnecting = False
        self._stop_ws_connection()
        if self._on_status_change:
            self._on_status_change(False)
        self._token_to_symbol.clear()
        self._subscriptions.clear()
        self._on_tick = None
        logger.info("WebSocket disconnected")
