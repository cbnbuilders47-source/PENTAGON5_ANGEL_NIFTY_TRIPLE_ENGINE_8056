"""In-memory application state (placeholder until live broker integration)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.constants import DEFAULT_ALLOCATIONS, ENGINE_NORMAL, ENGINE_ULTRA, ENGINE_WICK
from app.models.enums import BiasDirection, EngineStatus, MarketMode, SessionPhase


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
    engines: dict[str, EngineState] = field(default_factory=dict)
    candles: dict[str, list[CandleSnapshot]] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.now)

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
            from app.intelligence.time_rules import resolve_session_phase
            self.session_phase = resolve_session_phase(datetime.now())
            self.last_updated = datetime.now()

    def set_preferred_engine(self, engine: str) -> None:
        with self._lock:
            self.preferred_engine = engine

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
