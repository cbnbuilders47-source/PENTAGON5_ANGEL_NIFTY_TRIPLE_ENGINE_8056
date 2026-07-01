"""Engine state machine tests."""

from app.engines.state_machine import EngineStateMachine
from app.models.enums import EnginePhase


def test_idle_to_ready():
    sm = EngineStateMachine()
    assert sm.phase == EnginePhase.IDLE
    sm.advance_for_decision("READY")
    assert sm.phase == EnginePhase.READY


def test_would_buy_moves_to_entry_ready():
    sm = EngineStateMachine()
    sm.advance_for_decision("READY")
    sm.advance_for_decision("WOULD_BUY_CE")
    assert sm.phase == EnginePhase.ENTRY_READY


def test_reset():
    sm = EngineStateMachine()
    sm.advance_for_decision("READY")
    sm.reset()
    assert sm.phase == EnginePhase.IDLE
