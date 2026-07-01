"""Angel API rate-limit tracking."""

from __future__ import annotations

import threading
import time

from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_WINDOW_SEC = 60
DEFAULT_MAX_CALLS = 30


class RateLimitTracker:
    """Tracks REST call frequency to detect rate-limit risk."""

    def __init__(self, window_sec: int = DEFAULT_WINDOW_SEC, max_calls: int = DEFAULT_MAX_CALLS) -> None:
        self._window = window_sec
        self._max_calls = max_calls
        self._calls: list[float] = []
        self._blocked_until: float = 0.0
        self._lock = threading.Lock()

    def record_call(self) -> None:
        with self._lock:
            now = time.time()
            self._calls = [t for t in self._calls if now - t < self._window]
            self._calls.append(now)
            if len(self._calls) >= self._max_calls:
                self._blocked_until = now + self._window
                logger.warning("API rate-limit threshold reached — cooling down")

    def record_rate_limit_error(self, cooldown_sec: int = 60) -> None:
        with self._lock:
            self._blocked_until = time.time() + cooldown_sec
            logger.error("API rate-limit error recorded — blocked for %ss", cooldown_sec)

    @property
    def is_limited(self) -> bool:
        with self._lock:
            if time.time() < self._blocked_until:
                return True
            now = time.time()
            self._calls = [t for t in self._calls if now - t < self._window]
            return len(self._calls) >= self._max_calls

    @property
    def calls_in_window(self) -> int:
        with self._lock:
            now = time.time()
            self._calls = [t for t in self._calls if now - t < self._window]
            return len(self._calls)
