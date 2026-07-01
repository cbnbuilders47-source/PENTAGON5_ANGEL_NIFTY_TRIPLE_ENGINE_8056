"""Market intelligence — bias, mode, AI recommendation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.intelligence.bias import calculate_bias
from app.intelligence.market_mode import detect_market_mode
from app.intelligence.types import TradingContext
from app.market.ai_decision import AIDecision
from app.models.enums import AIRecommendation, BiasDirection, MarketMode
from app.models.schemas import CandleBar


@dataclass
class MarketSnapshot:
    bias_direction: BiasDirection
    bias_confidence: float
    bias_locked: bool
    market_mode: MarketMode
    ai_recommendation: AIRecommendation
    ai_confidence: float
    updated_at: datetime

    def to_dict(self) -> dict:
        return {
            "bias_direction": self.bias_direction.value,
            "bias_confidence": self.bias_confidence,
            "bias_locked": self.bias_locked,
            "market_mode": self.market_mode.value,
            "ai_recommendation": self.ai_recommendation.value,
            "ai_confidence": self.ai_confidence,
            "updated_at": self.updated_at.isoformat(),
        }


class MarketIntelligence:
    def __init__(self) -> None:
        self._ai = AIDecision()
        self.last_snapshot: MarketSnapshot | None = None

    def analyze(
        self,
        nifty: list[CandleBar],
        ce: list[CandleBar],
        pe: list[CandleBar],
        bias_locked: bool,
        now: datetime,
    ) -> MarketSnapshot:
        direction, confidence = calculate_bias(nifty)
        mode = detect_market_mode(nifty, ce, pe)
        ai = self._ai.evaluate(
            {
                "bias_direction": direction.value,
                "bias_confidence": confidence,
                "market_mode": mode.value,
                "nifty_candles": len(nifty),
            }
        )
        snap = MarketSnapshot(
            bias_direction=direction,
            bias_confidence=confidence,
            bias_locked=bias_locked,
            market_mode=mode,
            ai_recommendation=AIRecommendation(ai["recommendation"]),
            ai_confidence=float(ai["confidence"]),
            updated_at=now,
        )
        self.last_snapshot = snap
        return snap
