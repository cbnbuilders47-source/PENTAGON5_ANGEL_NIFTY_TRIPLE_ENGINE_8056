"""System control endpoints."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.trade_password import require_trade_password

router = APIRouter()


class ShutdownRequest(BaseModel):
    password: str | None = None


@router.post("/restart")
async def system_restart(request: Request) -> dict:
    recovery = request.app.state.execution_recovery
    summary = await recovery.recover()
    return {"status": "restarted", "recovery": summary}


@router.post("/shutdown")
async def system_shutdown(request: Request, body: ShutdownRequest) -> dict:
    require_trade_password(request, body.password, "system_shutdown")
    await request.app.state.shutdown_manager.shutdown(exit_process=True)
    return {"status": "shutdown_initiated"}
