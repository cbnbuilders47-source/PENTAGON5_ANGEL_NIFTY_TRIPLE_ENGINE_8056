"""Build trading context from live app state."""

from __future__ import annotations

from datetime import datetime

from app.core.clock import trading_now
from app.core.state import AppState
from app.intelligence.time_rules import bias_should_be_locked
from app.intelligence.types import TradingContext
from app.market.candle_builder import CandleBuilder
from app.models.enums import MarketMode


def build_context(
    state: AppState,
    candle_builder: CandleBuilder,
    market_mode: MarketMode,
    now: datetime | None = None,
) -> TradingContext:
    now = now or trading_now()
    phase = state.session_phase

    return TradingContext(
        nifty_candles=candle_builder.get_candles("NIFTY"),
        atm_ce_candles=candle_builder.get_candles("ATM_CE"),
        atm_pe_candles=candle_builder.get_candles("ATM_PE"),
        bias_direction=state.bias_direction,
        bias_confidence=state.bias_confidence_pct,
        bias_locked=state.bias_locked or bias_should_be_locked(now),
        market_mode=market_mode,
        available_margin=state.available_margin,
        allocated_margin=0.0,
        session_phase=phase,
        now=now,
        broker_connected=state.broker_connected,
    )
