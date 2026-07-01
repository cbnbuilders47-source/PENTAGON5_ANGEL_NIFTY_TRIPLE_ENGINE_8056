"""Engine state machine — no order execution."""

from __future__ import annotations

from app.models.enums import EnginePhase


_TRANSITIONS: dict[EnginePhase, list[EnginePhase]] = {
    EnginePhase.IDLE: [EnginePhase.READY],
    EnginePhase.READY: [EnginePhase.WAIT_CONFIRMATION, EnginePhase.ENTRY_READY, EnginePhase.IDLE],
    EnginePhase.WAIT_CONFIRMATION: [EnginePhase.ENTRY_READY, EnginePhase.READY, EnginePhase.IDLE],
    EnginePhase.ENTRY_READY: [EnginePhase.POSITION_ACTIVE, EnginePhase.WAIT_CONFIRMATION, EnginePhase.RESET],
    EnginePhase.POSITION_ACTIVE: [EnginePhase.EXIT_READY, EnginePhase.RESET],
    EnginePhase.EXIT_READY: [EnginePhase.COMPLETED, EnginePhase.POSITION_ACTIVE],
    EnginePhase.COMPLETED: [EnginePhase.RESET],
    EnginePhase.RESET: [EnginePhase.IDLE, EnginePhase.READY],
}


class EngineStateMachine:
    def __init__(self) -> None:
        self.phase = EnginePhase.IDLE

    def can_transition(self, target: EnginePhase) -> bool:
        return target in _TRANSITIONS.get(self.phase, [])

    def transition(self, target: EnginePhase) -> EnginePhase:
        if target == self.phase:
            return self.phase
        if self.can_transition(target):
            self.phase = target
        return self.phase

    def reset(self) -> None:
        self.phase = EnginePhase.IDLE

    def advance_for_decision(self, decision: str, has_position: bool = False) -> EnginePhase:
        if decision == "BLOCKED":
            return self.transition(EnginePhase.IDLE)
        if decision in ("WAIT",):
            if self.phase == EnginePhase.IDLE:
                return self.transition(EnginePhase.READY)
            return self.transition(EnginePhase.WAIT_CONFIRMATION)
        if decision in ("READY",):
            return self.transition(EnginePhase.READY)
        if decision.startswith("WOULD_BUY"):
            if has_position:
                return self.phase
            if self.phase in (EnginePhase.READY, EnginePhase.WAIT_CONFIRMATION):
                return self.transition(EnginePhase.ENTRY_READY)
            return self.transition(EnginePhase.ENTRY_READY)
        if decision == "WOULD_EXIT":
            if has_position:
                return self.transition(EnginePhase.EXIT_READY)
            return self.transition(EnginePhase.COMPLETED)
        return self.phase
