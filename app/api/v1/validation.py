"""Production validation API endpoints."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/status")
async def validation_status(request: Request) -> dict:
    svc = request.app.state.validation_service
    return svc.status()


@router.get("/manual")
async def manual_validation_status(request: Request) -> dict:
    svc = request.app.state.validation_service
    return svc.manual_status()


@router.post("/manual/reset")
async def reset_manual_validation(request: Request, engine: str | None = None) -> dict:
    tracker = request.app.state.manual_validation_tracker
    tracker.reset(engine)
    return {"reset": True, "engine": engine or "all"}


@router.post("/supervised-auto/enable")
async def enable_supervised_auto(request: Request) -> dict:
    """Allow AUTO mode without manual 0/3 — supervised live validation only."""
    state = request.app.state.app_state
    state.supervised_auto_enabled = True
    return {"supervised_auto_enabled": True}


@router.post("/supervised-auto/disable")
async def disable_supervised_auto(request: Request) -> dict:
    state = request.app.state.app_state
    state.supervised_auto_enabled = False
    return {"supervised_auto_enabled": False}
