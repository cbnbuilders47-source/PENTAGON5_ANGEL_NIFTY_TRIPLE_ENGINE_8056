"""Reports endpoints."""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.reports.excel_report import ExcelReport

router = APIRouter()


@router.get("/status")
async def reports_status() -> dict:
    return {"status": "ready", "message": "Report generation available"}


@router.get("/daily")
async def daily_report(request: Request) -> dict:
    state = request.app.state.app_state
    report = ExcelReport(request.app.state.settings)
    path = report.generate_daily(state.trade_history, state.to_dict())
    return {"path": str(path), "generated_at": datetime.now().isoformat()}


@router.get("/download")
async def download_report(request: Request) -> FileResponse:
    reports_dir = request.app.state.settings.reports_dir
    files = sorted(reports_dir.glob("daily_report_*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        report = ExcelReport(request.app.state.settings)
        path = report.generate_daily(request.app.state.app_state.trade_history, {})
        files = [path]
    return FileResponse(files[0], filename=files[0].name)
