"""Adaptive controller — orchestrates intelligence pipeline (no execution)."""

from __future__ import annotations

from app.core.constants import ENGINE_NORMAL, ENGINE_ULTRA, ENGINE_WICK
from app.core.logging import get_logger
from app.core.state import AppState
from app.engines.context_builder import build_context
from app.engines.normal_engine import NormalEngine
from app.engines.ultra_engine import UltraEngine
from app.engines.wick_engine import WickEngine
from app.intelligence.types import EngineDecisionSnapshot
from app.market.candle_builder import CandleBuilder
from app.market.market_intelligence import MarketIntelligence
from app.models.enums import EngineStatus, MarketMode

logger = get_logger(__name__)

_MODE_ENGINE_MAP: dict[MarketMode, str] = {
    MarketMode.TRENDING: ENGINE_ULTRA,
    MarketMode.BREAKOUT: ENGINE_ULTRA,
    MarketMode.SLOW_TREND: ENGINE_ULTRA,
    MarketMode.RANGE: ENGINE_WICK,
    MarketMode.REVERSAL: ENGINE_WICK,
    MarketMode.VOLATILE: ENGINE_NORMAL,
}


class AdaptiveController:
    def __init__(self, state: AppState, candle_builder: CandleBuilder) -> None:
        self._state = state
        self._candles = candle_builder
        self._market = MarketIntelligence()
        self.normal = NormalEngine()
        self.wick = WickEngine()
        self.ultra = UltraEngine()
        self.preferred_engine: str = ENGINE_NORMAL
        self.last_decisions: dict[str, EngineDecisionSnapshot] = {}

    def run_cycle(self) -> None:
        market = self._market.analyze(
            self._candles.get_candles("NIFTY"),
            self._candles.get_candles("ATM_CE"),
            self._candles.get_candles("ATM_PE"),
            self._state.bias_locked,
            build_context(self._state, self._candles, MarketMode.RANGE).now,
        )

        self._state.update_market_intelligence(
            direction=market.bias_direction,
            confidence=market.bias_confidence,
            locked=market.bias_locked,
            mode=market.market_mode,
            ai_recommendation=market.ai_recommendation.value,
            ai_confidence=market.ai_confidence,
        )

        self.preferred_engine = _MODE_ENGINE_MAP.get(market.market_mode, ENGINE_NORMAL)
        self._state.set_preferred_engine(self.preferred_engine)
        ctx = build_context(self._state, self._candles, market.market_mode)

        engines = {
            ENGINE_NORMAL: self.normal,
            ENGINE_WICK: self.wick,
            ENGINE_ULTRA: self.ultra,
        }

        for name, engine in engines.items():
            alloc_margin = self._state.engines.get(name).allocated_margin if name in self._state.engines else 0.0
            has_pos = name in self._state.live_positions
            snap = engine.evaluate(ctx, alloc_margin, has_live_position=has_pos)
            self.last_decisions[name] = snap
            self._state.update_engine_decision(name, snap)
            status = EngineStatus.ACTIVE if snap.decision.startswith("WOULD_") else EngineStatus.ANALYZING
            if snap.decision in ("WAIT", "BLOCKED"):
                status = EngineStatus.IDLE
            self._state.set_engine_status(name, status)

        logger.debug(
            "Adaptive recommendation: %s for mode %s",
            self.preferred_engine,
            market.market_mode.value,
        )

    async def start_all(self) -> None:
        logger.info("Adaptive controller intelligence cycle enabled")

    async def stop_all(self) -> None:
        self.normal.reset()
        self.wick.reset()
        self.ultra.reset()
        logger.info("Adaptive controller stopped")
