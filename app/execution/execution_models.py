"""Execution layer data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models.enums import EngineOperatingMode, ExecutionState, ExitReason, OrderSide


@dataclass
class ExecutionSignal:
    engine: str
    action: str  # BUY_CE | BUY_PE | BUY | EXIT
    symbol: str
    tradingsymbol: str
    token: str
    exchange: str = "NFO"
    strike: int | None = None
    expiry: str | None = None
    option_side: str | None = None  # CE | PE
    premium: float = 0.0
    confidence: float = 0.0
    opportunity_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    target: float | None = None
    stop_loss: float | None = None
    trailing_sl: float | None = None


@dataclass
class ExecutionRequest:
    signal: ExecutionSignal
    engine_mode: EngineOperatingMode
    lots: int = 0
    quantity: int = 0
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ExecutionResult:
    request_id: str
    engine: str
    state: ExecutionState
    message: str
    order_id: str | None = None
    executed_price: float | None = None
    quantity: int = 0
    latency_ms: float | None = None
    broker_response: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "engine": self.engine,
            "state": self.state.value,
            "message": self.message,
            "order_id": self.order_id,
            "executed_price": self.executed_price,
            "quantity": self.quantity,
            "latency_ms": self.latency_ms,
            "broker_response": self.broker_response,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class PendingManualApproval:
    approval_id: str
    engine: str
    action: str
    signal: ExecutionSignal
    lots: int
    quantity: int
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "approval_id": self.approval_id,
            "engine": self.engine,
            "action": self.action,
            "lots": self.lots,
            "quantity": self.quantity,
            "strike": self.signal.strike,
            "option_side": self.signal.option_side,
            "premium": self.signal.premium,
            "confidence": self.signal.confidence,
            "reasons": self.signal.reasons,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass
class LivePosition:
    engine: str
    tradingsymbol: str
    token: str
    exchange: str
    option_side: str
    strike: int
    expiry: str
    quantity: int
    lots: int
    entry_price: float
    current_ltp: float = 0.0
    target: float | None = None
    stop_loss: float | None = None
    trailing_sl: float | None = None
    entry_order_id: str | None = None
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    points: float = 0.0

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "tradingsymbol": self.tradingsymbol,
            "token": self.token,
            "exchange": self.exchange,
            "option_side": self.option_side,
            "strike": self.strike,
            "expiry": self.expiry,
            "quantity": self.quantity,
            "lots": self.lots,
            "entry_price": self.entry_price,
            "current_ltp": self.current_ltp,
            "target": self.target,
            "stop_loss": self.stop_loss,
            "trailing_sl": self.trailing_sl,
            "entry_order_id": self.entry_order_id,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "points": self.points,
        }
