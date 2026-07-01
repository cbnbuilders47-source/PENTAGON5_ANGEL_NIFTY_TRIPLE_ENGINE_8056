"""Graceful shutdown at 16:00 IST."""

from __future__ import annotations

from app.core.logging import get_logger
from app.reports.excel_report import ExcelReport

logger = get_logger(__name__)


class ShutdownManager:
    def __init__(self, app) -> None:
        self._app = app

    async def shutdown(self) -> None:
        logger.info("Graceful shutdown initiated")
        state = self._app.state.app_state
        settings = self._app.state.settings

        try:
            await self._app.state.execution_controller.exit_all(
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

        logger.info("Shutdown preparation complete")
