"""Candle builder unit tests."""

from datetime import datetime

from app.market.candle_builder import CandleBuilder


def test_candle_builder_single_tick():
    builder = CandleBuilder()
    result = builder.on_tick("NIFTY", 22000.0, 10, datetime(2026, 7, 1, 9, 15, 30))
    assert result is None


def test_candle_builder_completes_bar():
    builder = CandleBuilder()
    builder.on_tick("NIFTY", 22000.0, 10, datetime(2026, 7, 1, 9, 15, 30))
    builder.on_tick("NIFTY", 22050.0, 5, datetime(2026, 7, 1, 9, 15, 45))
    completed = builder.on_tick("NIFTY", 22025.0, 8, datetime(2026, 7, 1, 9, 16, 5))
    assert completed is not None
    assert completed.open == 22000.0
    assert completed.high == 22050.0
    assert completed.close == 22050.0
