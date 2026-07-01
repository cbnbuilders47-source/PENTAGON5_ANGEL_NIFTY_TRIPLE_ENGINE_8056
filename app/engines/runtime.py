"""Background intelligence evaluation loop."""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger

logger = get_logger(__name__)


async def intelligence_loop(app) -> None:
    while True:
        try:
            await asyncio.sleep(2)
            controller = app.state.adaptive_controller
            controller.run_cycle()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.exception("Intelligence loop error: %s", exc)
