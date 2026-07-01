"""Aggregate API v1 routers."""

from fastapi import APIRouter

from app.api.v1 import broker, dashboard, engines, health, market, reports

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router, tags=["health"])
api_router.include_router(broker.router, prefix="/broker", tags=["broker"])
api_router.include_router(engines.router, prefix="/engines", tags=["engines"])
api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
