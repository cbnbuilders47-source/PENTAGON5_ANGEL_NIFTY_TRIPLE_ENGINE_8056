"""Excel report generation."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ExcelReport:
    """Generates end-of-day Excel reports."""

    def __init__(self, settings: Settings) -> None:
        self._reports_dir = settings.reports_dir

    def generate(self, data: dict, filename: str = "daily_report.xlsx") -> Path:
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        path = self._reports_dir / filename
        logger.info("Excel report generation pending — output path: %s", path)
        return path
