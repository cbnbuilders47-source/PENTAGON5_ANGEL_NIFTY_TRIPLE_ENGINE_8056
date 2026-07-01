"""Excel report generation tests."""

from app.core.config import get_settings
from app.reports.excel_report import ExcelReport


def test_generate_daily_report(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "reports_dir", tmp_path)
    report = ExcelReport(settings)
    path = report.generate_daily(
        [{"engine": "normal", "entry_price": 100, "exit_price": 110, "quantity": 65, "pnl": 650}],
        {},
        filename="test_report.xlsx",
    )
    assert path.exists()
    assert path.suffix == ".xlsx"
