"""Shared types for the intelligence layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.models.enums import BiasDirection, EnginePhase, MarketMode, SessionPhase
from app.models.schemas import CandleBar


@dataclass
class TradingContext:
    nifty_candles: list[CandleBar]
    atm_ce_candles: list[CandleBar]
    atm_pe_candles: list[CandleBar]
    bias_direction: BiasDirection
    bias_confidence: float
    bias_locked: bool
    market_mode: MarketMode
    available_margin: float
    allocated_margin: float
    session_phase: SessionPhase
    now: datetime
    broker_connected: bool


@dataclass
class AnalysisMetrics:
    momentum: float = 0.0
    liquidity: float = 0.0
    market_health: float = 0.0
    entry_quality: float = 0.0
    opportunity_score: float = 0.0
    trend_confirmed: bool = False
    momentum_confirmed: bool = False


@dataclass
class EngineDecisionSnapshot:
    engine: str
    phase: EnginePhase
    decision: str
    reasons: list[str] = field(default_factory=list)
    confidence: float = 0.0
    opportunity_score: float = 0.0
    entry_quality: float = 0.0
    momentum: float = 0.0
    liquidity: float = 0.0
    market_health: float = 0.0
    expected_target: float | None = None
    expected_sl: float | None = None
    trailing_sl: float | None = None
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "phase": self.phase.value,
            "decision": self.decision,
            "reasons": self.reasons,
            "confidence": self.confidence,
            "opportunity_score": self.opportunity_score,
            "entry_quality": self.entry_quality,
            "momentum": self.momentum,
            "liquidity": self.liquidity,
            "market_health": self.market_health,
            "expected_target": self.expected_target,
            "expected_sl": self.expected_sl,
            "trailing_sl": self.trailing_sl,
            "updated_at": self.updated_at.isoformat(),
        }
