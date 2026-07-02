"""Engine control endpoints."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.trade_password import require_trade_password
from app.models.enums import EngineOperatingMode, ExitReason

router = APIRouter()


class EngineModeRequest(BaseModel):
    mode: EngineOperatingMode
    password: str | None = None


class PasswordBody(BaseModel):
    password: str | None = None


@router.post("/{engine}/mode")
async def set_engine_mode(request: Request, engine: str, body: EngineModeRequest) -> dict:
    if body.mode == EngineOperatingMode.AUTO:
        require_trade_password(request, body.password, f"engine_mode_auto:{engine}")
    ctrl = request.app.state.execution_controller
    block_reason = ctrl.set_engine_mode(engine, body.mode)
    if block_reason:
        raise HTTPException(status_code=403, detail={"reason": block_reason, "engine": engine, "mode": body.mode.value})
    return {"engine": engine, "mode": body.mode.value}


@router.post("/{engine}/start")
async def start_engine(request: Request, engine: str) -> dict:
    request.app.state.app_state.set_engine_status(engine, __import__("app.models.enums", fromlist=["EngineStatus"]).EngineStatus.ANALYZING)
    return {"engine": engine, "status": "started"}


@router.post("/{engine}/stop")
async def stop_engine(request: Request, engine: str) -> dict:
    from app.models.enums import EngineStatus
    request.app.state.execution_controller.set_engine_mode(engine, EngineOperatingMode.OFF)
    request.app.state.app_state.set_engine_status(engine, EngineStatus.STOPPED)
    return {"engine": engine, "status": "stopped"}


@router.post("/{engine}/exit")
async def exit_engine(request: Request, engine: str, body: PasswordBody) -> dict:
    require_trade_password(request, body.password, f"engine_exit:{engine}")
    result = await request.app.state.execution_controller.exit_engine(engine, ExitReason.MANUAL)
    return result.to_dict() if result else {"message": "no result"}
