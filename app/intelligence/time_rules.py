"""Session time restrictions."""

from __future__ import annotations

from datetime import datetime, time

from app.core.constants import (
    BIAS_LOCK,
    FORCE_EXIT,
    PRE_MARKET_END,
    PRE_MARKET_START,
    STOP_NEW_ENTRIES,
    TRADING_START,
)
from app.models.enums import SessionPhase


def resolve_session_phase(now: datetime) -> SessionPhase:
    t = now.time()
    if t < time(8, 30):
        return SessionPhase.OFFLINE
    if PRE_MARKET_START <= t <= PRE_MARKET_END:
        return SessionPhase.PRE_MARKET
    if time(9, 7, 31) <= t < TRADING_START:
        return SessionPhase.BIAS_LOCKED
    if TRADING_START <= t < STOP_NEW_ENTRIES:
        return SessionPhase.TRADING
    if STOP_NEW_ENTRIES <= t < FORCE_EXIT:
        return SessionPhase.NO_NEW_ENTRIES
    if FORCE_EXIT <= t < time(15, 30):
        return SessionPhase.FORCE_EXIT
    if time(15, 30) <= t < time(16, 0):
        return SessionPhase.PREWATCH
    return SessionPhase.SHUTDOWN


def new_entries_allowed(phase: SessionPhase) -> bool:
    return phase == SessionPhase.TRADING


def force_exit_required(phase: SessionPhase) -> bool:
    return phase in (SessionPhase.FORCE_EXIT, SessionPhase.SHUTDOWN)


def pre_market_analysis(phase: SessionPhase) -> bool:
    return phase == SessionPhase.PRE_MARKET


def bias_should_be_locked(now: datetime) -> bool:
    return now.time() >= BIAS_LOCK
