"""Execution audit logging."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.execution.execution_models import ExecutionResult

logger = get_logger(__name__)


class ExecutionAudit:
    def __init__(self) -> None:
        settings = get_settings()
        self._audit_dir = settings.logs_dir
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._audit_dir / "execution_audit.log"

    def log(self, event: str, payload: dict) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} | {event} | {payload}"
        logger.info("EXEC_AUDIT %s", line)
        with self._file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def log_result(self, result: ExecutionResult) -> None:
        self.log("execution_result", result.to_dict())
