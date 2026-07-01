"""Session time restrictions."""

from __future__ import annotations

from datetime import datetime, time

from app.core.constants import (
    BIAS_LOCK,
    ENGINE_NORMAL,
    ENGINE_ULTRA,
    ENGINE_WICK,
    FORCE_EXIT,
    PRE_MARKET_END,
    PRE_MARKET_START,
    SPECIAL_NO_ENTRY_END,
    SPECIAL_NO_ENTRY_START,
    STOP_NEW_ENTRIES,
    TRADING_START,
    WICK_TRADING_END,
)
from app.models.enums import SessionPhase

SPECIAL_NO_ENTRY_BLOCK_MESSAGE = {
    ENGINE_NORMAL: "Normal Engine blocked during Special No-Entry Window (14:57–15:01)",
    ENGINE_ULTRA: "Ultra Engine blocked during Special No-Entry Window (14:57–15:01)",
}


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


def is_special_no_entry_window(now: datetime) -> bool:
    t = now.time()
    return SPECIAL_NO_ENTRY_START <= t < SPECIAL_NO_ENTRY_END


def is_special_no_entry_blocked_engine(engine: str) -> bool:
    return engine in (ENGINE_NORMAL, ENGINE_ULTRA)


def engine_buy_blocked_special_window(engine: str, now: datetime) -> bool:
    return is_special_no_entry_blocked_engine(engine) and is_special_no_entry_window(now)


def special_no_entry_block_message(engine: str, now: datetime) -> str | None:
    if engine_buy_blocked_special_window(engine, now):
        return SPECIAL_NO_ENTRY_BLOCK_MESSAGE.get(engine)
    return None


def engine_new_entries_allowed(engine: str, now: datetime) -> bool:
    """Engine-specific new-entry window (does not affect open-position monitoring)."""
    t = now.time()
    if t < TRADING_START or t >= FORCE_EXIT:
        return False

    if engine == ENGINE_WICK:
        return t < WICK_TRADING_END

    if t >= STOP_NEW_ENTRIES:
        return False
    if engine_buy_blocked_special_window(engine, now):
        return False
    return True


def wick_entries_allowed(now: datetime) -> bool:
    return engine_new_entries_allowed(ENGINE_WICK, now)


def force_exit_required(phase: SessionPhase) -> bool:
    return phase in (SessionPhase.FORCE_EXIT, SessionPhase.SHUTDOWN)


def pre_market_analysis(phase: SessionPhase) -> bool:
    return phase == SessionPhase.PRE_MARKET


def bias_should_be_locked(now: datetime) -> bool:
    return now.time() >= BIAS_LOCK
