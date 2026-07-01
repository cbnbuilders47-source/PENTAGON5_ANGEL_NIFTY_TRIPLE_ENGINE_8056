"""Background intelligence + execution signal processing."""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.execution.signal_bridge import decision_to_signal

logger = get_logger(__name__)


async def intelligence_loop(app) -> None:
    while True:
        try:
            await asyncio.sleep(2)
            controller_adaptive = app.state.adaptive_controller
            controller_adaptive.run_cycle()

            exec_ctrl = app.state.execution_controller
            atm = app.state.atm_manager
            instruments = app.state.instrument_master
            candles = app.state.candle_builder

            for name, snap in controller_adaptive.last_decisions.items():
                signal = decision_to_signal(name, snap, instruments, atm, candles)
                if signal:
                    await exec_ctrl.process_signal(signal)

            await app.state.exit_monitor.evaluate()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.exception("Intelligence loop error: %s", exc)
