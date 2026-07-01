"""Live exit monitoring framework."""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.state import AppState
from app.execution.execution_controller import ExecutionController
from app.models.enums import ExitReason
from app.scheduler.session_scheduler import SessionScheduler

logger = get_logger(__name__)


class ExitMonitor:
    """Checks open positions for exit conditions — routes through ExecutionController."""

    def __init__(
        self,
        state: AppState,
        controller: ExecutionController,
        scheduler: SessionScheduler,
    ) -> None:
        self._state = state
        self._controller = controller
        self._scheduler = scheduler

    async def evaluate(self) -> None:
        if self._state.kill_switch_active:
            await self._controller.exit_all(ExitReason.KILL_SWITCH)
            return

        if self._scheduler.force_exit_active:
            await self._controller.exit_all(ExitReason.FORCE_EXIT)
            return

        for engine, pos in list(self._state.live_positions.items()):
            ltp = float(pos.get("current_ltp") or pos.get("entry_price") or 0)
            entry = float(pos.get("entry_price") or 0)
            target = pos.get("target")
            sl = pos.get("stop_loss")
            trailing = pos.get("trailing_sl")

            reason = None
            if target and ltp >= float(target):
                reason = ExitReason.TARGET
            elif sl and ltp <= float(sl):
                reason = ExitReason.STOP_LOSS
            elif trailing and ltp <= float(trailing):
                reason = ExitReason.TRAILING

            if reason:
                logger.info("Exit signal %s for engine %s at LTP %.2f", reason.value, engine, ltp)
                await self._controller.exit_engine(engine, reason)
