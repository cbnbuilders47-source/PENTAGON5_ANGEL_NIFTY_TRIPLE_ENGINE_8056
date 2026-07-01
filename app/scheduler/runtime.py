"""Scheduler background loop."""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger

logger = get_logger(__name__)


async def scheduler_loop(app) -> None:
    while True:
        try:
            await asyncio.sleep(1)
            scheduler = app.state.session_scheduler
            status = scheduler.tick()
            state = app.state.app_state
            state.apply_scheduler_status(status)

            if status.force_exit_active:
                app.state.force_exit_manager.evaluate(status.current_phase)

            app.state.risk_manager.refresh_gates()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.exception("Scheduler loop error: %s", exc)
