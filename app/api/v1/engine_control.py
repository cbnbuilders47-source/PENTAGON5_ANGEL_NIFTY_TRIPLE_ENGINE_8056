"""Engine control endpoints."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.models.enums import EngineOperatingMode, ExitReason

router = APIRouter()


class EngineModeRequest(BaseModel):
    mode: EngineOperatingMode


@router.post("/{engine}/mode")
async def set_engine_mode(request: Request, engine: str, body: EngineModeRequest) -> dict:
    ctrl = request.app.state.execution_controller
    ctrl.set_engine_mode(engine, body.mode)
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
async def exit_engine(request: Request, engine: str) -> dict:
    result = await request.app.state.execution_controller.exit_engine(engine, ExitReason.MANUAL)
    return result.to_dict() if result else {"message": "no result"}
