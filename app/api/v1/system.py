"""System control endpoints."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.logging import get_logger
from app.core.trade_password import require_trade_password

router = APIRouter()
logger = get_logger(__name__)


class DashboardPasswordRequest(BaseModel):
    password: str | None = None


@router.post("/wakeup")
async def system_wakeup(request: Request, body: DashboardPasswordRequest) -> dict:
    require_trade_password(request, body.password, "dashboard_wakeup")
    logger.info("Dashboard wakeup authorized")
    return {"status": "unlocked"}


@router.post("/restart")
async def system_restart(request: Request) -> dict:
    recovery = request.app.state.execution_recovery
    summary = await recovery.recover()
    return {"status": "restarted", "recovery": summary}


@router.post("/shutdown")
async def system_shutdown(request: Request, body: DashboardPasswordRequest) -> dict:
    require_trade_password(request, body.password, "dashboard_shutdown")
    logger.info("Dashboard shutdown requested")
    await request.app.state.shutdown_manager.shutdown(exit_process=True)
    logger.info("Dashboard shutdown completed")
    return {"status": "shutdown_initiated"}
