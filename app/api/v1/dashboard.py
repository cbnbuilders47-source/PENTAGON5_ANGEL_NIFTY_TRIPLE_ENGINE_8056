"""Dashboard API and state endpoints."""

from pathlib import Path

from fastapi import APIRouter, Query, Request

from app.core.config import get_settings
from app.models.schemas import (
    AllocationResponse,
    BiasInfo,
    EngineInfo,
    EnginePnlInfo,
    LogsResponse,
    PnlResponse,
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
        market_mode=state.market_mode,
        ai_recommendation=state.ai_recommendation,
        ai_confidence=state.ai_confidence,
        preferred_engine=state.preferred_engine,
        engine_decisions=state.engine_decisions,
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


@router.get("/pnl", response_model=PnlResponse)
async def get_pnl(request: Request) -> PnlResponse:
    state = request.app.state.app_state
    engines = [
        EnginePnlInfo(
            name=e.name,
            status=e.status,
            pnl=e.pnl,
            allocation_pct=e.allocation_pct,
            allocated_margin=e.allocated_margin,
            open_positions=e.open_positions,
        )
        for e in state.engines.values()
    ]
    return PnlResponse(
        total=state.today_total_pnl,
        realized=state.today_realized_pnl,
        unrealized=state.today_unrealized_pnl,
        engines=engines,
    )


@router.get("/logs", response_model=LogsResponse)
async def get_logs(
    lines: int = Query(default=80, ge=10, le=500),
) -> LogsResponse:
    settings = get_settings()
    log_file: Path = settings.logs_dir / "app.log"
    if not log_file.exists():
        return LogsResponse(lines=[], count=0)

    content = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = content[-lines:]
    return LogsResponse(lines=tail, count=len(tail))
