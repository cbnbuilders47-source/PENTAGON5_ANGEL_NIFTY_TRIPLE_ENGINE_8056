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
