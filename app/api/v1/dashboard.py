"""Dashboard API and state endpoints."""

from datetime import datetime
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
        readiness=state.readiness_report,
        risk=state.risk_status,
        force_exit=state.force_exit_status,
        new_entries_allowed=state.new_entries_allowed,
        force_exit_active=state.force_exit_active,
        kill_switch_active=state.kill_switch_active,
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
        engine_modes=dict(state.engine_modes),
        live_positions=dict(state.live_positions),
        pending_approvals=list(state.pending_approvals),
        nifty_ltp=state.nifty_ltp,
        nifty_change_pts=state.nifty_change_pts,
        nifty_change_pct=state.nifty_change_pct,
        used_margin=state.used_margin,
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
    log_type: str = Query(default="system", description="broker|trade|engine|risk|system|error|audit|health|execution"),
) -> LogsResponse:
    settings = get_settings()
    log_map = {
        "broker": "broker.log",
        "trade": "trade.log",
        "engine": "engine.log",
        "risk": "risk.log",
        "system": "app.log",
        "error": "error.log",
        "audit": "execution_audit.log",
        "health": "health.log",
        "execution": "execution_audit.log",
    }
    filename = log_map.get(log_type, "app.log")
    log_file: Path = settings.logs_dir / filename
    if not log_file.exists():
        return LogsResponse(lines=[], count=0)

    content = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = content[-lines:]
    return LogsResponse(lines=tail, count=len(tail))


@router.get("/operator")
async def get_operator_diagnostics(request: Request) -> dict:
    """Operator visibility bundle — display-only, does not affect trading."""
    state = request.app.state.app_state
    atm = request.app.state.atm_manager
    instruments = request.app.state.instrument_master
    candle_builder = request.app.state.candle_builder
    scheduler = request.app.state.session_scheduler
    exec_ctrl = request.app.state.execution_controller

    sched = scheduler.tick()
    nifty_candles = candle_builder.get_candles("NIFTY")
    ce_candles = candle_builder.get_candles("ATM_CE")
    pe_candles = candle_builder.get_candles("ATM_PE")
    ce_prem = ce_candles[-1].close if ce_candles else 0.0
    pe_prem = pe_candles[-1].close if pe_candles else 0.0

    tick_ages: dict[str, float | None] = {}
    for sym in ("NIFTY", "ATM_CE", "ATM_PE"):
        last = candle_builder.get_last_tick_at(sym)
        tick_ages[sym] = round((datetime.now() - last).total_seconds(), 1) if last else None

    exec_status = exec_ctrl.status()
    recent = exec_status.get("recent", [])
    latest = recent[-1] if recent else None

    uptime_sec = 0.0
    if state.started_at:
        uptime_sec = round((datetime.now() - state.started_at).total_seconds(), 1)

    day_high = max((c.high for c in nifty_candles), default=None)
    day_low = min((c.low for c in nifty_candles), default=None)

    return {
        "uptime_sec": uptime_sec,
        "started_at": state.started_at.isoformat() if state.started_at else None,
        "atm_strike": atm.atm_strike,
        "expiry": instruments.selected_expiry,
        "ce_premium": ce_prem,
        "pe_premium": pe_prem,
        "premium_spread": round(abs(ce_prem - pe_prem), 2) if ce_prem or pe_prem else None,
        "pcr": round(pe_prem / ce_prem, 2) if ce_prem > 0 and pe_prem > 0 else None,
        "tick_ages": tick_ages,
        "scheduler_phase": sched.current_phase.value,
        "new_entries_allowed": sched.new_entries_allowed,
        "force_exit_active": sched.force_exit_active,
        "next_events": [e for e in sched.events_today if not e.get("fired")][:3],
        "latest_order": latest,
        "execution_recent": recent[-8:],
        "last_order_at": state.last_order_at.isoformat() if state.last_order_at else None,
        "nifty_day_high": day_high,
        "nifty_day_low": day_low,
        "readiness": state.readiness_report,
        **request.app.state.validation_service.operator_bundle(),
    }
