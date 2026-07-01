"""Force exit framework tests."""

from app.core.state import AppState
from app.models.enums import SessionPhase
from app.risk.force_exit import ForceExitManager


def test_force_exit_inactive_outside_window():
    mgr = ForceExitManager(AppState())
    status = mgr.evaluate(SessionPhase.TRADING)
    assert status.active is False


def test_force_exit_active_in_window():
    state = AppState()
    mgr = ForceExitManager(state)
    status = mgr.evaluate(SessionPhase.FORCE_EXIT)
    assert status.active is True
    assert len(status.actions) == 3
    assert all(a.action == "EXIT_ALL" for a in status.actions)
