"""Graceful shutdown for dashboard server (port 8056 only)."""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from app.core.constants import ENGINES
from app.core.logging import get_logger
from app.models.enums import EngineOperatingMode
from app.reports.excel_report import ExcelReport

logger = get_logger(__name__)


class ShutdownManager:
    def __init__(self, app) -> None:
        self._app = app

    async def shutdown(self, *, exit_process: bool = True) -> None:
        logger.info("Graceful shutdown initiated")
        state = self._app.state.app_state
        settings = self._app.state.settings
        ctrl = self._app.state.execution_controller

        for engine in ENGINES:
            try:
                ctrl.set_engine_mode(engine, EngineOperatingMode.OFF)
            except Exception as exc:
                logger.warning("Engine stop during shutdown (%s): %s", engine, exc)

        try:
            await ctrl.exit_all(
                __import__("app.models.enums", fromlist=["ExitReason"]).ExitReason.FORCE_EXIT
            )
        except Exception as exc:
            logger.warning("Exit-all during shutdown: %s", exc)

        try:
            report = ExcelReport(settings)
            report.generate_daily(state.trade_history, state.to_dict())
        except Exception as exc:
            logger.warning("Report generation during shutdown: %s", exc)

        try:
            await self._app.state.broker_session.disconnect()
        except Exception as exc:
            logger.warning("Broker disconnect during shutdown: %s", exc)

        self._flush_logs()
        logger.info("Shutdown preparation complete (port %s)", settings.port)

        if exit_process:
            self._schedule_process_exit()

    def _flush_logs(self) -> None:
        for handler in logging.root.handlers:
            try:
                handler.flush()
            except Exception:
                pass
        logger.info("Log handlers flushed")

    def _schedule_process_exit(self) -> None:
        settings = self._app.state.settings

        async def _exit() -> None:
            await asyncio.sleep(0.75)
            logger.info("Terminating uvicorn process on port %s", settings.port)
            os.kill(os.getpid(), signal.SIGTERM)

        asyncio.create_task(_exit())
