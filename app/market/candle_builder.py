"""Build 1-minute OHLC candles from live WebSocket ticks."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime

from app.core.logging import get_logger
from app.models.schemas import CandleBar

logger = get_logger(__name__)


@dataclass
class _CandleBuilder:
    symbol: str
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    bar_start: datetime | None = None
    history: list[CandleBar] = field(default_factory=list)

    def on_tick(self, price: float, volume: int, ts: datetime) -> CandleBar | None:
        bar_start = ts.replace(second=0, microsecond=0)
        if self.bar_start is None:
            self._start_bar(bar_start, price, volume)
            return None

        if bar_start > self.bar_start:
            completed = self._complete_bar()
            self._start_bar(bar_start, price, volume)
            return completed

        self.high = max(self.high, price)
        self.low = min(self.low, price) if self.low else price
        self.close = price
        self.volume += volume
        return None

    def _start_bar(self, bar_start: datetime, price: float, volume: int) -> None:
        self.bar_start = bar_start
        self.open = price
        self.high = price
        self.low = price
        self.close = price
        self.volume = volume

    def _complete_bar(self) -> CandleBar:
        bar = CandleBar(
            symbol=self.symbol,
            timestamp=self.bar_start,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )
        self.history.append(bar)
        if len(self.history) > 120:
            self.history = self.history[-120:]
        return bar

    def current_bar(self) -> CandleBar | None:
        if self.bar_start is None:
            return None
        return CandleBar(
            symbol=self.symbol,
            timestamp=self.bar_start,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )


class CandleBuilder:
    """Manages 1m candle builders for NIFTY, ATM CE, ATM PE."""

    def __init__(self) -> None:
        self._builders: dict[str, _CandleBuilder] = {}
        self._lock = threading.Lock()

    def get_or_create(self, symbol: str) -> _CandleBuilder:
        if symbol not in self._builders:
            self._builders[symbol] = _CandleBuilder(symbol=symbol)
        return self._builders[symbol]

    def on_tick(self, symbol: str, price: float, volume: int = 0, ts: datetime | None = None) -> CandleBar | None:
        ts = ts or datetime.now()
        with self._lock:
            return self.get_or_create(symbol).on_tick(price, volume, ts)

    def get_candles(self, symbol: str, limit: int = 60) -> list[CandleBar]:
        with self._lock:
            builder = self._builders.get(symbol)
            if not builder:
                return []
            candles = list(builder.history)
            current = builder.current_bar()
            if current:
                candles.append(current)
            return candles[-limit:]
