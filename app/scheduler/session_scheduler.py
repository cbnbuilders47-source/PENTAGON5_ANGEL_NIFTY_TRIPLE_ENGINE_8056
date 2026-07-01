"""Session scheduler for IST trading day phases."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Callable

from app.core.constants import (
    AUTO_STARTUP,
    BIAS_LOCK,
    FORCE_EXIT,
    NEXT_DAY_PREWATCH,
    PRE_MARKET_END,
    PRE_MARKET_START,
    STOP_NEW_ENTRIES,
    TRADING_START,
)
from app.core.logging import get_logger
from app.models.enums import SessionPhase

logger = get_logger(__name__)

AUTO_SHUTDOWN = time(16, 0, 0)


@dataclass
class SchedulerEvent:
    phase: SessionPhase
    label: str
    at: time
    fired: bool = False


@dataclass
class SchedulerStatus:
    current_phase: SessionPhase
    bias_locked: bool
    new_entries_allowed: bool
    force_exit_active: bool
    shutdown_prep: bool
    events_today: list[dict] = field(default_factory=list)
    last_tick_at: datetime | None = None


class SessionScheduler:
    """Drives session phase transitions on IST schedule."""

    def __init__(self) -> None:
        self._events = [
            SchedulerEvent(SessionPhase.OFFLINE, "startup_prep", AUTO_STARTUP),
            SchedulerEvent(SessionPhase.PRE_MARKET, "pre_market_analysis", PRE_MARKET_START),
            SchedulerEvent(SessionPhase.BIAS_LOCKED, "bias_lock", BIAS_LOCK),
            SchedulerEvent(SessionPhase.TRADING, "trading_start", TRADING_START),
            SchedulerEvent(SessionPhase.NO_NEW_ENTRIES, "stop_new_entries", STOP_NEW_ENTRIES),
            SchedulerEvent(SessionPhase.FORCE_EXIT, "force_exit_all", FORCE_EXIT),
            SchedulerEvent(SessionPhase.PREWATCH, "next_day_prewatch", NEXT_DAY_PREWATCH),
            SchedulerEvent(SessionPhase.SHUTDOWN, "graceful_shutdown_prep", AUTO_SHUTDOWN),
        ]
        self._current_phase = SessionPhase.OFFLINE
        self._bias_locked = False
        self._new_entries_allowed = False
        self._force_exit_active = False
        self._shutdown_prep = False
        self._last_date: str | None = None
        self._on_phase_change: Callable[[SessionPhase], None] | None = None

    @property
    def current_phase(self) -> SessionPhase:
        return self._current_phase

    @property
    def bias_locked(self) -> bool:
        return self._bias_locked

    @property
    def new_entries_allowed(self) -> bool:
        return self._new_entries_allowed

    @property
    def force_exit_active(self) -> bool:
        return self._force_exit_active

    @property
    def shutdown_prep(self) -> bool:
        return self._shutdown_prep

    def set_phase_callback(self, callback: Callable[[SessionPhase], None]) -> None:
        self._on_phase_change = callback

    def tick(self, now: datetime | None = None) -> SchedulerStatus:
        now = now or datetime.now()
        self._reset_if_new_day(now)

        t = now.time()
        phase = self._resolve_phase(t)
        if phase != self._current_phase:
            logger.info("Session phase: %s -> %s", self._current_phase.value, phase.value)
            self._current_phase = phase
            if self._on_phase_change:
                self._on_phase_change(phase)

        self._bias_locked = t >= BIAS_LOCK and t < AUTO_SHUTDOWN
        self._new_entries_allowed = TRADING_START <= t < STOP_NEW_ENTRIES
        self._force_exit_active = t >= FORCE_EXIT and t < NEXT_DAY_PREWATCH
        self._shutdown_prep = t >= AUTO_SHUTDOWN

        self._fire_events(t)

        return SchedulerStatus(
            current_phase=self._current_phase,
            bias_locked=self._bias_locked,
            new_entries_allowed=self._new_entries_allowed,
            force_exit_active=self._force_exit_active,
            shutdown_prep=self._shutdown_prep,
            events_today=[
                {"label": e.label, "phase": e.phase.value, "at": e.at.isoformat(), "fired": e.fired}
                for e in self._events
            ],
        )

    def _reset_if_new_day(self, now: datetime) -> None:
        date_key = now.date().isoformat()
        if self._last_date != date_key:
            self._last_date = date_key
            for event in self._events:
                event.fired = False
            logger.info("Scheduler reset for new trading day %s", date_key)

    def _resolve_phase(self, t: time) -> SessionPhase:
        if t < AUTO_STARTUP:
            return SessionPhase.OFFLINE
        if AUTO_STARTUP <= t < PRE_MARKET_START:
            return SessionPhase.OFFLINE
        if PRE_MARKET_START <= t <= PRE_MARKET_END:
            return SessionPhase.PRE_MARKET
        if BIAS_LOCK <= t < TRADING_START:
            return SessionPhase.BIAS_LOCKED
        if TRADING_START <= t < STOP_NEW_ENTRIES:
            return SessionPhase.TRADING
        if STOP_NEW_ENTRIES <= t < FORCE_EXIT:
            return SessionPhase.NO_NEW_ENTRIES
        if FORCE_EXIT <= t < NEXT_DAY_PREWATCH:
            return SessionPhase.FORCE_EXIT
        if NEXT_DAY_PREWATCH <= t < AUTO_SHUTDOWN:
            return SessionPhase.PREWATCH
        return SessionPhase.SHUTDOWN

    def _fire_events(self, t: time) -> None:
        for event in self._events:
            if not event.fired and t >= event.at:
                event.fired = True
                logger.info("Scheduler event fired: %s (%s)", event.label, event.phase.value)
