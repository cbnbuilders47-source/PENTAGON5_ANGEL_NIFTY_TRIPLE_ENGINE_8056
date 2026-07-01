"""In-memory application state (placeholder until live broker integration)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.constants import DEFAULT_ALLOCATIONS, ENGINE_NORMAL, ENGINE_ULTRA, ENGINE_WICK
from app.models.enums import BiasDirection, EngineOperatingMode, EngineStatus, MarketMode, SessionPhase


@dataclass
class EngineState:
    name: str
    status: EngineStatus = EngineStatus.IDLE
    allocation_pct: float = 0.0
    allocated_margin: float = 0.0
    pnl: float = 0.0
    open_positions: int = 0


@dataclass
class CandleSnapshot:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


@dataclass
class AppState:
    """Thread-safe global application state."""

    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    session_phase: SessionPhase = SessionPhase.OFFLINE
    broker_connected: bool = False
    websocket_connected: bool = False
    available_margin: float = 0.0
    today_realized_pnl: float = 0.0
    today_unrealized_pnl: float = 0.0

    bias_direction: BiasDirection = BiasDirection.NEUTRAL
    bias_confidence_pct: float = 0.0
    bias_locked: bool = False

    allocations: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_ALLOCATIONS)
    )

    market_mode: str = "SLOW_TREND"
    ai_recommendation: str = "WAIT"
    ai_confidence: float = 0.0
    preferred_engine: str = ENGINE_NORMAL
    engine_decisions: dict[str, dict] = field(default_factory=dict)
    readiness_report: dict = field(default_factory=dict)
    risk_status: dict = field(default_factory=dict)
    force_exit_status: dict = field(default_factory=dict)
    new_entries_allowed: bool = False
    force_exit_active: bool = False
    kill_switch_active: bool = False
    engine_modes: dict[str, str] = field(default_factory=lambda: {
        ENGINE_NORMAL: EngineOperatingMode.MONITOR.value,
        ENGINE_WICK: EngineOperatingMode.MONITOR.value,
        ENGINE_ULTRA: EngineOperatingMode.MONITOR.value,
    })
    live_positions: dict[str, dict] = field(default_factory=dict)
    pending_approvals: list[dict] = field(default_factory=list)
    trade_history: list[dict] = field(default_factory=list)
    execution_results: list[dict] = field(default_factory=list)
    recovery_summary: dict = field(default_factory=dict)
    nifty_ltp: float = 0.0
    nifty_change_pts: float = 0.0
    nifty_change_pct: float = 0.0
    used_margin: float = 0.0
    engines: dict[str, EngineState] = field(default_factory=dict)
    candles: dict[str, list[CandleSnapshot]] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.now)
    started_at: datetime = field(default_factory=datetime.now)
    last_order_at: datetime | None = None
    validation_last_success: datetime | None = None
    broker_reconnect_required: bool = False
    recovery_status: dict = field(default_factory=lambda: {
        "status": "unknown",
        "clean": True,
        "message": "Startup — recovery not run",
    })
    reconnect_status: dict = field(default_factory=dict)
    auto_validation_max_lots: dict[str, int] = field(default_factory=lambda: {
        ENGINE_NORMAL: 1,
        ENGINE_WICK: 1,
        ENGINE_ULTRA: 1,
    })

    def __post_init__(self) -> None:
        for name, pct in self.allocations.items():
            self.engines[name] = EngineState(name=name, allocation_pct=pct)

    def update_allocations(self, normal: float, wick: float, ultra: float) -> None:
        total = normal + wick + ultra
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"Allocations must sum to 100%, got {total}%")
        with self._lock:
            self.allocations = {
                ENGINE_NORMAL: normal,
                ENGINE_WICK: wick,
                ENGINE_ULTRA: ultra,
            }
            for name, pct in self.allocations.items():
                if name in self.engines:
                    self.engines[name].allocation_pct = pct
                else:
                    self.engines[name] = EngineState(name=name, allocation_pct=pct)
            self._recalculate_margins()
            self.last_updated = datetime.now()

    def set_available_margin(self, margin: float) -> None:
        with self._lock:
            self.available_margin = margin
            self._recalculate_margins()
            self.last_updated = datetime.now()

    def set_day_pnl(self, realized: float, unrealized: float) -> None:
        with self._lock:
            self.today_realized_pnl = realized
            self.today_unrealized_pnl = unrealized
            self.last_updated = datetime.now()

    @property
    def today_total_pnl(self) -> float:
        with self._lock:
            engine_pnl = sum(e.pnl for e in self.engines.values())
            return self.today_realized_pnl + self.today_unrealized_pnl + engine_pnl

    def _recalculate_margins(self) -> None:
        for name, engine in self.engines.items():
            pct = self.allocations.get(name, 0.0)
            engine.allocated_margin = self.available_margin * (pct / 100.0)

    def set_engine_status(self, name: str, status: EngineStatus) -> None:
        with self._lock:
            if name in self.engines:
                self.engines[name].status = status
            self.last_updated = datetime.now()

    def update_engine_decision(self, name: str, snapshot) -> None:
        with self._lock:
            self.engine_decisions[name] = snapshot.to_dict()
            self.last_updated = datetime.now()

    def update_market_intelligence(
        self,
        direction: BiasDirection,
        confidence: float,
        locked: bool,
        mode: MarketMode,
        ai_recommendation: str,
        ai_confidence: float,
    ) -> None:
        with self._lock:
            self.bias_direction = direction
            self.bias_confidence_pct = confidence
            self.bias_locked = locked
            self.market_mode = mode.value
            self.ai_recommendation = ai_recommendation
            self.ai_confidence = ai_confidence
            self.last_updated = datetime.now()

    def set_preferred_engine(self, engine: str) -> None:
        with self._lock:
            self.preferred_engine = engine

    def get_engine_mode(self, engine: str) -> EngineOperatingMode:
        with self._lock:
            val = self.engine_modes.get(engine, EngineOperatingMode.MONITOR.value)
            return EngineOperatingMode(val)

    def set_engine_mode(self, engine: str, mode: EngineOperatingMode) -> None:
        with self._lock:
            self.engine_modes[engine] = mode.value
            self.last_updated = datetime.now()

    def set_live_position(self, engine: str, position: dict) -> None:
        with self._lock:
            self.live_positions[engine] = position
            self.last_updated = datetime.now()

    def clear_live_position(self, engine: str) -> None:
        with self._lock:
            self.live_positions.pop(engine, None)
            self.last_updated = datetime.now()

    def update_position_ltp_from_tick(self, feed_symbol: str, price: float) -> None:
        """Refresh open-position LTP from ATM option ticks for exit monitoring."""
        with self._lock:
            updated = False
            for pos in self.live_positions.values():
                side = str(pos.get("option_side", "")).upper()
                if feed_symbol == f"ATM_{side}":
                    pos["current_ltp"] = price
                    entry = float(pos.get("entry_price") or 0)
                    qty = int(pos.get("quantity") or 0)
                    unrealized = (price - entry) * qty
                    peak = float(pos.get("peak_profit") or unrealized)
                    if unrealized > peak:
                        pos["peak_profit"] = unrealized
                    updated = True
            if updated:
                self.last_updated = datetime.now()

    def set_pending_approval(self, approval: dict) -> None:
        with self._lock:
            self.pending_approvals = [a for a in self.pending_approvals if a.get("approval_id") != approval.get("approval_id")]
            self.pending_approvals.append(approval)
            self.last_updated = datetime.now()

    def clear_pending_approval(self, approval_id: str) -> None:
        with self._lock:
            self.pending_approvals = [a for a in self.pending_approvals if a.get("approval_id") != approval_id]
            self.last_updated = datetime.now()

    def set_execution_result(self, result: dict) -> None:
        with self._lock:
            self.execution_results.append(result)
            if len(self.execution_results) > 200:
                self.execution_results = self.execution_results[-200:]
            state_val = result.get("state", "")
            if state_val in ("ORDER_CONFIRMED", "POSITION_ACTIVE", "EXIT_CONFIRMED"):
                self.last_order_at = datetime.now()
            self.last_updated = datetime.now()

    def record_trade(self, engine: str, pos: dict, exit_price: float, exit_order_id: str, pnl: float, reason: str) -> None:
        with self._lock:
            self.trade_history.append({
                "engine": engine,
                "entry_order_id": pos.get("entry_order_id"),
                "exit_order_id": exit_order_id,
                "entry_price": pos.get("entry_price"),
                "exit_price": exit_price,
                "quantity": pos.get("quantity"),
                "lots": pos.get("lots"),
                "strike": pos.get("strike"),
                "expiry": pos.get("expiry"),
                "option_side": pos.get("option_side"),
                "pnl": pnl,
                "exit_reason": reason,
                "closed_at": datetime.now().isoformat(),
            })
            self.today_realized_pnl += pnl
            self.last_updated = datetime.now()

    def set_recovery_summary(self, summary: dict) -> None:
        with self._lock:
            self.recovery_summary = summary
            self.last_updated = datetime.now()

    def set_recovery_status(self, status: dict) -> None:
        with self._lock:
            self.recovery_status = status
            self.last_updated = datetime.now()

    def set_reconnect_status(self, status: dict) -> None:
        with self._lock:
            self.reconnect_status = status
            self.last_updated = datetime.now()

    def set_broker_reconnect_required(self, required: bool, reason: str = "") -> None:
        with self._lock:
            self.broker_reconnect_required = required
            if required:
                self.recovery_status = {
                    **self.recovery_status,
                    "status": "dirty",
                    "clean": False,
                    "message": reason or "Broker reconnect required",
                }
            self.last_updated = datetime.now()

    def mark_validation_success(self) -> None:
        with self._lock:
            self.validation_last_success = datetime.now()
            self.last_updated = datetime.now()

    def update_nifty_quote(self, ltp: float) -> None:
        with self._lock:
            if self.nifty_ltp > 0:
                self.nifty_change_pts = ltp - self.nifty_ltp
                self.nifty_change_pct = (self.nifty_change_pts / self.nifty_ltp) * 100
            self.nifty_ltp = ltp
            self.last_updated = datetime.now()

    def apply_scheduler_status(self, status) -> None:
        with self._lock:
            self.session_phase = status.current_phase
            self.bias_locked = status.bias_locked
            self.new_entries_allowed = status.new_entries_allowed
            self.force_exit_active = status.force_exit_active
            self.last_updated = datetime.now()

    def set_readiness_report(self, report: dict) -> None:
        with self._lock:
            self.readiness_report = report
            self.last_updated = datetime.now()

    def set_risk_status(self, status: dict) -> None:
        with self._lock:
            self.risk_status = status
            self.kill_switch_active = not status.get("trading_allowed", False) and any(
                g.get("name") == "kill_switch" and not g.get("passed") for g in status.get("gates", [])
            )
            self.last_updated = datetime.now()

    def set_force_exit_status(self, status: dict) -> None:
        with self._lock:
            self.force_exit_status = status
            self.last_updated = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "session_phase": self.session_phase.value,
                "broker_connected": self.broker_connected,
                "websocket_connected": self.websocket_connected,
                "available_margin": self.available_margin,
                "bias": {
                    "direction": self.bias_direction.value,
                    "confidence_pct": self.bias_confidence_pct,
                    "locked": self.bias_locked,
                },
                "market_mode": self.market_mode,
                "ai_recommendation": self.ai_recommendation,
                "ai_confidence": self.ai_confidence,
                "preferred_engine": self.preferred_engine,
                "engine_decisions": dict(self.engine_decisions),
                "readiness": dict(self.readiness_report),
                "risk": dict(self.risk_status),
                "force_exit": dict(self.force_exit_status),
                "new_entries_allowed": self.new_entries_allowed,
                "force_exit_active": self.force_exit_active,
                "kill_switch_active": self.kill_switch_active,
                "engine_modes": dict(self.engine_modes),
                "live_positions": dict(self.live_positions),
                "pending_approvals": list(self.pending_approvals),
                "trade_history": self.trade_history[-50:],
                "nifty_ltp": self.nifty_ltp,
                "nifty_change_pts": self.nifty_change_pts,
                "nifty_change_pct": self.nifty_change_pct,
                "used_margin": self.used_margin,
                "allocations": dict(self.allocations),
                "engines": {
                    name: {
                        "status": e.status.value,
                        "allocation_pct": e.allocation_pct,
                        "allocated_margin": e.allocated_margin,
                        "pnl": e.pnl,
                        "open_positions": e.open_positions,
                    }
                    for name, e in self.engines.items()
                },
                "last_updated": self.last_updated.isoformat(),
            }


_state: AppState | None = None
_state_lock = threading.Lock()


def get_app_state() -> AppState:
    global _state
    if _state is None:
        with _state_lock:
            if _state is None:
                _state = AppState()
    return _state
