"""Production validation API endpoints."""

from fastapi import APIRouter, Request

from app.storage.operator_settings_store import OperatorSettingsStore

router = APIRouter()


def _persist_supervised_auto(enabled: bool) -> None:
    store = OperatorSettingsStore()
    payload = store.load()
    payload["supervised_auto_enabled"] = enabled
    store.save(payload)


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


@router.post("/reset")
async def reset_validation_runtime(request: Request) -> dict:
    """Reset manual validation 0/3, pending approvals, and execution validation state."""
    svc = request.app.state.validation_service
    exec_ctrl = request.app.state.execution_controller
    return svc.reset_validation_runtime(exec_ctrl)


@router.post("/supervised-auto/enable")
async def enable_supervised_auto(request: Request) -> dict:
    """Allow AUTO mode without manual 0/3 — supervised live validation only."""
    state = request.app.state.app_state
    state.supervised_auto_enabled = True
    _persist_supervised_auto(True)
    return {"supervised_auto_enabled": True}


@router.post("/supervised-auto/disable")
async def disable_supervised_auto(request: Request) -> dict:
    state = request.app.state.app_state
    state.supervised_auto_enabled = False
    _persist_supervised_auto(False)
    return {"supervised_auto_enabled": False}
