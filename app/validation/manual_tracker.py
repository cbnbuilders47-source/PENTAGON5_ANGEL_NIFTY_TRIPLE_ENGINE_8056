"""Per-engine manual validation cycle tracking."""

from __future__ import annotations

from datetime import datetime

from app.core.constants import ENGINES

MANUAL_STEPS: tuple[str, ...] = (
    "buy_signal_generated",
    "manual_approval_shown",
    "user_approval_received",
    "angel_buy_order_sent",
    "buy_order_confirmed",
    "executed_price_captured",
    "position_active",
    "ltp_updating",
    "pnl_updating",
    "exit_signal_generated",
    "manual_exit_approval_received",
    "sell_order_sent",
    "sell_order_confirmed",
    "report_row_created",
    "logs_created",
)


def _empty_steps() -> dict[str, bool]:
    return {step: False for step in MANUAL_STEPS}


class ManualValidationTracker:
    """Tracks the 15-step manual validation cycle per engine."""

    def __init__(self) -> None:
        self._steps: dict[str, dict[str, bool]] = {e: _empty_steps() for e in ENGINES}
        self._passed: dict[str, bool] = {e: False for e in ENGINES}
        self._updated_at: dict[str, datetime | None] = {e: None for e in ENGINES}

    def reset(self, engine: str | None = None) -> None:
        targets = [engine] if engine else list(ENGINES)
        for name in targets:
            if name not in self._steps:
                continue
            self._steps[name] = _empty_steps()
            self._passed[name] = False
            self._updated_at[name] = datetime.now()

    def mark(self, engine: str, step: str) -> None:
        if engine not in self._steps or step not in self._steps[engine]:
            return
        self._steps[engine][step] = True
        self._updated_at[engine] = datetime.now()
        if all(self._steps[engine].values()):
            self._passed[engine] = True

    def is_passed(self, engine: str) -> bool:
        return self._passed.get(engine, False)

    def any_passed(self) -> bool:
        return any(self._passed.values())

    def engine_status(self, engine: str) -> dict:
        steps = self._steps.get(engine, _empty_steps())
        completed = sum(1 for v in steps.values() if v)
        return {
            "engine": engine,
            "passed": self._passed.get(engine, False),
            "steps": dict(steps),
            "completed": completed,
            "total": len(MANUAL_STEPS),
            "updated_at": self._updated_at.get(engine).isoformat() if self._updated_at.get(engine) else None,
        }

    def all_status(self) -> dict[str, dict]:
        return {e: self.engine_status(e) for e in ENGINES}
