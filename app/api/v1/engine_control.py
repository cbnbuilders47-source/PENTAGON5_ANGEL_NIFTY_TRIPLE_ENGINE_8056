"""Engine control endpoints."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.models.enums import EngineOperatingMode, ExitReason

router = APIRouter()


class EngineModeRequest(BaseModel):
    mode: EngineOperatingMode


@router.post("/{engine}/mode")
async def set_engine_mode(request: Request, engine: str, body: EngineModeRequest) -> dict:
    ctrl = request.app.state.execution_controller
    state = request.app.state.app_state
    block_reason = ctrl.set_engine_mode(engine, body.mode)
    if block_reason:
        raise HTTPException(
            status_code=403,
            detail={"reason": block_reason, "engine": engine, "mode": body.mode.value},
        )
    persisted = ctrl.get_engine_mode(engine).value
    if persisted != body.mode.value:
        raise HTTPException(
            status_code=500,
            detail={
                "reason": f"Mode not persisted — expected {body.mode.value}, got {persisted}",
                "engine": engine,
                "state_id": id(state),
            },
        )
    return {
        "engine": engine,
        "mode": persisted,
        "state_id": id(state),
        "engine_modes": dict(state.engine_modes),
    }


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
