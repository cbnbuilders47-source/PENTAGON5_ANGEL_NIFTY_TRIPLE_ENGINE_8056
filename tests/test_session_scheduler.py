"""Session scheduler tests."""

from datetime import datetime

from app.models.enums import SessionPhase
from app.scheduler.session_scheduler import SessionScheduler


def test_startup_prep_phase():
    sched = SessionScheduler()
    status = sched.tick(datetime(2026, 7, 1, 8, 35, 0))
    assert status.current_phase == SessionPhase.OFFLINE


def test_pre_market_phase():
    sched = SessionScheduler()
    status = sched.tick(datetime(2026, 7, 1, 9, 5, 0))
    assert status.current_phase == SessionPhase.PRE_MARKET


def test_trading_window():
    sched = SessionScheduler()
    status = sched.tick(datetime(2026, 7, 1, 10, 0, 0))
    assert status.current_phase == SessionPhase.TRADING
    assert status.new_entries_allowed is True


def test_stop_new_entries():
    sched = SessionScheduler()
    status = sched.tick(datetime(2026, 7, 1, 15, 12, 0))
    assert status.current_phase == SessionPhase.NO_NEW_ENTRIES
    assert status.new_entries_allowed is False


def test_force_exit_window():
    sched = SessionScheduler()
    status = sched.tick(datetime(2026, 7, 1, 15, 15, 0))
    assert status.current_phase == SessionPhase.FORCE_EXIT
    assert status.force_exit_active is True
