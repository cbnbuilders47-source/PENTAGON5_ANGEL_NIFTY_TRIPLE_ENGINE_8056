"""Adaptive controller tests."""

from datetime import datetime

from app.core.state import AppState
from app.engines.adaptive_controller import AdaptiveController
from app.market.candle_builder import CandleBuilder
from app.models.schemas import CandleBar


def _seed_candles(builder: CandleBuilder) -> None:
    base = 22000.0
    for i in range(12):
        ts = datetime(2026, 7, 1, 9, 15, i)
        builder.on_tick("NIFTY", base + i * 5, 100, ts)
        builder.on_tick("ATM_CE", 120 + i, 50, ts)
        builder.on_tick("ATM_PE", 110 + i * 0.5, 50, ts)


def test_adaptive_controller_run_cycle():
    state = AppState()
    state.broker_connected = True
    state.available_margin = 100000
    state.set_available_margin(100000)
    builder = CandleBuilder()
    _seed_candles(builder)

    controller = AdaptiveController(state, builder)
    controller.run_cycle()

    assert state.market_mode
    assert state.preferred_engine in ("normal", "wick", "ultra")
    assert "normal" in state.engine_decisions
    assert controller.last_decisions["normal"].decision
