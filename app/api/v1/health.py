"""Health and readiness endpoints."""

from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.models.schemas import HealthResponse, ReadinessResponse
from app.storage.db import check_database

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def ready(request: Request) -> ReadinessResponse:
    settings = get_settings()
    db_ok = check_database()
    broker_configured = settings.angel_configured

    details = {
        "database": "ok" if db_ok else "unavailable",
        "broker": "configured" if broker_configured else "not_configured",
        "trading_mode": settings.trading_mode,
    }

    return ReadinessResponse(
        ready=db_ok,
        broker_configured=broker_configured,
        database=db_ok,
        details=details,
    )
