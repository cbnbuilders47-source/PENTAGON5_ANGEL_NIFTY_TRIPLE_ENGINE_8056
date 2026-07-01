"""Trading locks — prevent concurrent order conflicts."""

from __future__ import annotations

import threading

from app.core.logging import get_logger

logger = get_logger(__name__)


class TradingLocks:
    """Per-engine and global trading locks."""

    def __init__(self) -> None:
        self._global = threading.Lock()
        self._engines: dict[str, threading.Lock] = {}

    def engine_lock(self, engine: str) -> threading.Lock:
        if engine not in self._engines:
            self._engines[engine] = threading.Lock()
        return self._engines[engine]

    @property
    def global_lock(self) -> threading.Lock:
        return self._global
