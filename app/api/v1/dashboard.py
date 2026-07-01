"""Dashboard API and state endpoints."""

from fastapi import APIRouter, Request

from app.models.schemas import (
    AllocationResponse,
    BiasInfo,
    EngineInfo,
    StateResponse,
)

router = APIRouter()


@router.get("/state", response_model=StateResponse)
async def get_state(request: Request) -> StateResponse:
    state = request.app.state.app_state
    alloc = state.allocations
    return StateResponse(
        session_phase=state.session_phase,
        broker_connected=state.broker_connected,
        websocket_connected=state.websocket_connected,
        available_margin=state.available_margin,
        bias=BiasInfo(
            direction=state.bias_direction,
            confidence_pct=state.bias_confidence_pct,
            locked=state.bias_locked,
        ),
        allocations=AllocationResponse(
            normal=alloc.get("normal", 0),
            wick=alloc.get("wick", 0),
            ultra=alloc.get("ultra", 0),
        ),
        engines=[
            EngineInfo(
                name=e.name,
                status=e.status,
                allocation_pct=e.allocation_pct,
                allocated_margin=e.allocated_margin,
                pnl=e.pnl,
                open_positions=e.open_positions,
            )
            for e in state.engines.values()
        ],
        last_updated=state.last_updated,
    )
