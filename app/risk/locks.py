"""Trading locks — duplicate, engine, symbol, kill switch."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta

from app.core.logging import get_logger

logger = get_logger(__name__)

DUPLICATE_WINDOW_SEC = 120


class TradingLocks:
    """Per-engine, symbol, and global trading locks. LIVE ONLY."""

    def __init__(self) -> None:
        self._global = threading.Lock()
        self._engines: dict[str, threading.Lock] = {}
        self._kill_switch = False
        self._engine_halt: set[str] = set()
        self._symbol_halt: set[str] = set()
        self._duplicate_hashes: dict[str, datetime] = {}
        self._dup_lock = threading.Lock()

    @property
    def global_lock(self) -> threading.Lock:
        return self._global

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch

    def activate_kill_switch(self, reason: str = "manual") -> None:
        self._kill_switch = True
        logger.critical("KILL SWITCH ACTIVATED: %s", reason)

    def deactivate_kill_switch(self) -> None:
        self._kill_switch = False
        logger.warning("Kill switch deactivated")

    def engine_lock(self, engine: str) -> threading.Lock:
        if engine not in self._engines:
            self._engines[engine] = threading.Lock()
        return self._engines[engine]

    def halt_engine(self, engine: str) -> None:
        self._engine_halt.add(engine)
        logger.warning("Engine halted: %s", engine)

    def release_engine(self, engine: str) -> None:
        self._engine_halt.discard(engine)

    def is_engine_halted(self, engine: str) -> bool:
        return engine in self._engine_halt

    def halt_symbol(self, symbol: str) -> None:
        self._symbol_halt.add(symbol.upper())
        logger.warning("Symbol halted: %s", symbol)

    def release_symbol(self, symbol: str) -> None:
        self._symbol_halt.discard(symbol.upper())

    def is_symbol_halted(self, symbol: str) -> bool:
        return symbol.upper() in self._symbol_halt

    def register_duplicate_signal(self, signal_hash: str) -> bool:
        """Return True if duplicate (blocked). Prefer is_duplicate_signal + mark_duplicate_signal."""
        if self.is_duplicate_signal(signal_hash):
            return True
        self.mark_duplicate_signal(signal_hash)
        return False

    def is_duplicate_signal(self, signal_hash: str) -> bool:
        """Return True if this signal hash is within the duplicate window."""
        now = datetime.now()
        with self._dup_lock:
            cutoff = now - timedelta(seconds=DUPLICATE_WINDOW_SEC)
            self._duplicate_hashes = {k: v for k, v in self._duplicate_hashes.items() if v > cutoff}
            return signal_hash in self._duplicate_hashes

    def mark_duplicate_signal(self, signal_hash: str) -> None:
        """Record a signal hash after an order is actually sent to the broker."""
        with self._dup_lock:
            self._duplicate_hashes[signal_hash] = datetime.now()

    def release_duplicate_signal(self, signal_hash: str) -> None:
        """Allow retry after a failed/rejected execution."""
        with self._dup_lock:
            self._duplicate_hashes.pop(signal_hash, None)

    def clear_duplicates(self) -> None:
        with self._dup_lock:
            self._duplicate_hashes.clear()
