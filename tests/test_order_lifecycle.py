"""Order lifecycle state machine tests."""

from app.execution.order_lifecycle import OrderLifecycle
from app.models.enums import ExecutionState


def test_happy_path_entry():
    lc = OrderLifecycle()
    lc.transition(ExecutionState.GATE_CHECKING)
    lc.transition(ExecutionState.APPROVED)
    lc.transition(ExecutionState.ORDER_SENT)
    lc.transition(ExecutionState.ORDER_PENDING)
    lc.transition(ExecutionState.ORDER_CONFIRMED)
    lc.transition(ExecutionState.POSITION_ACTIVE)
    assert lc.state == ExecutionState.POSITION_ACTIVE


def test_blocked_by_risk():
    lc = OrderLifecycle()
    lc.transition(ExecutionState.GATE_CHECKING)
    lc.transition(ExecutionState.BLOCKED_BY_RISK)
    assert lc.is_terminal()


def test_exit_path():
    lc = OrderLifecycle()
    lc.state = ExecutionState.POSITION_ACTIVE
    lc.transition(ExecutionState.EXIT_SIGNAL_RECEIVED)
    lc.transition(ExecutionState.EXIT_ORDER_SENT)
    lc.transition(ExecutionState.EXIT_CONFIRMED)
    lc.transition(ExecutionState.COMPLETED)
    assert lc.state == ExecutionState.COMPLETED
