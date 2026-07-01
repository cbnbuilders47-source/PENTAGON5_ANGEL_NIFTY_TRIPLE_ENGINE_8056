"""Aggregate API v1 routers."""

from fastapi import APIRouter

from app.api.v1 import (
    broker,
    dashboard,
    engine_control,
    engines,
    execution,
    health,
    market,
    reports,
    risk,
    scheduler,
    system,
    trading_data,
    validation,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router, tags=["health"])
api_router.include_router(broker.router, prefix="/broker", tags=["broker"])
api_router.include_router(engines.router, prefix="/engines", tags=["engines"])
api_router.include_router(engine_control.router, prefix="/engine", tags=["engine-control"])
api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(risk.router, prefix="/risk", tags=["risk"])
api_router.include_router(scheduler.router, prefix="/scheduler", tags=["scheduler"])
api_router.include_router(execution.router, prefix="/execution", tags=["execution"])
api_router.include_router(trading_data.router, tags=["trading-data"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(validation.router, prefix="/validation", tags=["validation"])
