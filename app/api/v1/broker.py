"""Broker status endpoints."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/status")
async def broker_status(request: Request) -> dict:
    state = request.app.state.app_state
    settings = request.app.state.settings
    return {
        "connected": state.broker_connected,
        "websocket_connected": state.websocket_connected,
        "configured": settings.angel_configured,
        "available_margin": state.available_margin,
        "trading_mode": settings.trading_mode,
    }
