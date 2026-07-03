"""Broker status and session endpoints."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/status")
async def broker_status(request: Request) -> dict:
    state = request.app.state.app_state
    settings = request.app.state.settings
    tokens = request.app.state.token_manager
    atm = request.app.state.atm_manager
    return {
        "connected": state.broker_connected,
        "websocket_connected": state.websocket_connected,
        "configured": settings.angel_configured,
        "tokens_valid": tokens.is_valid,
        "available_margin": state.available_margin,
        "trading_mode": settings.trading_mode,
        "atm_strike": atm.atm_strike,
        "atm_ce_token": atm.ce_token,
        "atm_pe_token": atm.pe_token,
    }


@router.post("/connect")
async def broker_connect(request: Request) -> dict:
    session = request.app.state.broker_session
    return await session.connect()


@router.post("/disconnect")
async def broker_disconnect(request: Request) -> dict:
    session = request.app.state.broker_session
    await session.disconnect()
    return {"success": True}


@router.get("/readiness")
async def broker_readiness(request: Request) -> dict:
    gate = request.app.state.readiness_gate
    report = gate.evaluate()
    return report.to_dict()


@router.post("/recovery/resync")
async def broker_recovery_resync(request: Request) -> dict:
    """Sync broker positions with AppState and refresh recovery status."""
    recovery = request.app.state.execution_recovery
    summary = await recovery.resync()
    state = request.app.state.app_state
    return {
        "success": summary.get("clean", False),
        "recovery": summary,
        "live_positions": dict(state.live_positions),
    }
