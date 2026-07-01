"""Force exit trigger tests."""

from app.core.state import AppState
from app.models.enums import SessionPhase
from app.risk.force_exit import ForceExitManager


def test_force_exit_trigger_once():
    state = AppState()
    mgr = ForceExitManager(state)
    mgr.evaluate(SessionPhase.FORCE_EXIT)
    assert mgr.consume_force_exit_trigger() is True
    assert mgr.consume_force_exit_trigger() is False


def test_force_exit_reset_on_phase_change():
    state = AppState()
    mgr = ForceExitManager(state)
    mgr.evaluate(SessionPhase.FORCE_EXIT)
    mgr.consume_force_exit_trigger()
    mgr.evaluate(SessionPhase.TRADING)
    mgr.evaluate(SessionPhase.FORCE_EXIT)
    assert mgr.consume_force_exit_trigger() is True
