"""Risk status and kill switch endpoints."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.trade_password import require_trade_password

router = APIRouter()


class KillSwitchRequest(BaseModel):
    active: bool
    reason: str = "manual"
    password: str | None = None


@router.get("/status")
async def risk_status(request: Request) -> dict:
    manager = request.app.state.risk_manager
    status = manager.refresh_gates()
    return status.to_dict()


@router.post("/kill-switch")
async def kill_switch(request: Request, body: KillSwitchRequest) -> dict:
    if body.active:
        require_trade_password(request, body.password, "kill_switch_activate")
    locks = request.app.state.trading_locks
    if body.active:
        locks.activate_kill_switch(body.reason)
    else:
        locks.deactivate_kill_switch()
    status = request.app.state.risk_manager.refresh_gates()
    return {
        "kill_switch_active": locks.kill_switch_active,
        "risk": status.to_dict(),
    }
