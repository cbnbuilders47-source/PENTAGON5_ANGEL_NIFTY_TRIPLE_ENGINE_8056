"""Force-exit framework — no live order placement."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.logging import get_logger
from app.core.state import AppState
from app.models.enums import SessionPhase

logger = get_logger(__name__)


@dataclass
class ForceExitAction:
    engine: str
    action: str
    reason: str


@dataclass
class ForceExitStatus:
    active: bool
    actions: list[ForceExitAction] = field(default_factory=list)
    message: str = ""
    evaluated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "active": self.active,
            "message": self.message,
            "evaluated_at": self.evaluated_at.isoformat(),
            "actions": [
                {"engine": a.engine, "action": a.action, "reason": a.reason}
                for a in self.actions
            ],
        }


class ForceExitManager:
    """Framework for 15:14 force-exit — logs WOULD_EXIT_ALL only."""

    ENGINES = ("normal", "wick", "ultra")

    def __init__(self, state: AppState) -> None:
        self._state = state
        self.last_status: ForceExitStatus | None = None
        self._triggered = False
        self._exit_dispatched = False

    def evaluate(self, phase: SessionPhase) -> ForceExitStatus:
        if phase != SessionPhase.FORCE_EXIT:
            self._triggered = False
            self._exit_dispatched = False
            status = ForceExitStatus(active=False, message="Force exit not required")
            self.last_status = status
            self._state.set_force_exit_status(status.to_dict())
            return status

        actions = [
            ForceExitAction(
                engine=name,
                action="EXIT_ALL",
                reason="15:14 IST force-exit window",
            )
            for name in self.ENGINES
        ]

        if not self._triggered:
            logger.warning("FORCE EXIT window active — exiting all positions")
            self._triggered = True

        status = ForceExitStatus(
            active=True,
            actions=actions,
            message="Force-exit active — all engines exiting",
        )
        self.last_status = status
        self._state.set_force_exit_status(status.to_dict())
        return status

    def reset(self) -> None:
        self._triggered = False

    def consume_force_exit_trigger(self) -> bool:
        """Return True once when force-exit window first activates."""
        if self._triggered and getattr(self, "_exit_dispatched", False) is False:
            self._exit_dispatched = True
            return True
        return False
