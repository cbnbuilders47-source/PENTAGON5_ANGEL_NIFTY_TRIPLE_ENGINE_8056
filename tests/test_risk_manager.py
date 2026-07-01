"""Risk manager tests."""

from app.core.state import AppState
from app.risk.locks import TradingLocks
from app.risk.risk_manager import RiskManager
from app.scheduler.session_scheduler import SessionScheduler


def test_allocation_gate():
    state = AppState()
    sched = SessionScheduler()
    locks = TradingLocks()
    rm = RiskManager(state, locks, sched)
    status = rm.evaluate()
    alloc_gate = next(g for g in status.gates if g.name == "allocation_valid")
    assert alloc_gate.passed is True


def test_kill_switch_blocks_entry():
    state = AppState()
    sched = SessionScheduler()
    locks = TradingLocks()
    locks.activate_kill_switch("test")
    rm = RiskManager(state, locks, sched)
    allowed, reason = rm.can_open_position("normal", "ATM_CE")
    assert allowed is False
    assert "Kill switch" in reason


def test_force_exit_blocks_entry():
    state = AppState()
    sched = SessionScheduler()
    sched.tick(__import__("datetime").datetime(2026, 7, 1, 15, 15, 0))
    locks = TradingLocks()
    rm = RiskManager(state, locks, sched)
    allowed, reason = rm.can_open_position("normal", "ATM_CE")
    assert allowed is False
