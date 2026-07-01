"""Execution order lifecycle state machine."""

from __future__ import annotations

from app.models.enums import ExecutionState

_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
    ExecutionState.SIGNAL_RECEIVED: {ExecutionState.GATE_CHECKING, ExecutionState.BLOCKED_BY_ENGINE_MODE},
    ExecutionState.GATE_CHECKING: {
        ExecutionState.APPROVED,
        ExecutionState.BLOCKED_BY_RISK,
        ExecutionState.BLOCKED_BY_BROKER,
        ExecutionState.BLOCKED_BY_TIME,
        ExecutionState.BLOCKED_BY_MARGIN,
        ExecutionState.BLOCKED_BY_ENGINE_MODE,
    },
    ExecutionState.APPROVED: {ExecutionState.ORDER_SENT},
    ExecutionState.ORDER_SENT: {
        ExecutionState.ORDER_PENDING,
        ExecutionState.ORDER_REJECTED,
        ExecutionState.UNKNOWN_ORDER_STATE,
    },
    ExecutionState.ORDER_PENDING: {
        ExecutionState.ORDER_CONFIRMED,
        ExecutionState.ORDER_REJECTED,
        ExecutionState.ORDER_TIMEOUT,
        ExecutionState.UNKNOWN_ORDER_STATE,
    },
    ExecutionState.ORDER_CONFIRMED: {ExecutionState.POSITION_ACTIVE},
    ExecutionState.POSITION_ACTIVE: {ExecutionState.EXIT_SIGNAL_RECEIVED},
    ExecutionState.EXIT_SIGNAL_RECEIVED: {ExecutionState.EXIT_ORDER_SENT},
    ExecutionState.EXIT_ORDER_SENT: {
        ExecutionState.EXIT_CONFIRMED,
        ExecutionState.ORDER_REJECTED,
        ExecutionState.ORDER_TIMEOUT,
    },
    ExecutionState.EXIT_CONFIRMED: {ExecutionState.COMPLETED},
}


class OrderLifecycle:
    def __init__(self) -> None:
        self.state = ExecutionState.SIGNAL_RECEIVED

    def transition(self, target: ExecutionState) -> ExecutionState:
        allowed = _TRANSITIONS.get(self.state, set())
        if target in allowed or target == self.state:
            self.state = target
        return self.state

    def is_terminal(self) -> bool:
        return self.state in {
            ExecutionState.COMPLETED,
            ExecutionState.BLOCKED_BY_RISK,
            ExecutionState.BLOCKED_BY_BROKER,
            ExecutionState.BLOCKED_BY_TIME,
            ExecutionState.BLOCKED_BY_MARGIN,
            ExecutionState.BLOCKED_BY_ENGINE_MODE,
            ExecutionState.ORDER_REJECTED,
            ExecutionState.RECOVERY_REQUIRED,
        }
