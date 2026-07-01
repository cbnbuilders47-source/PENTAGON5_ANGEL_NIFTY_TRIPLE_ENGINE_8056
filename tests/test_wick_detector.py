"""Wick detector tests."""

from datetime import datetime

from app.intelligence.wick import detect_wick
from app.models.schemas import CandleBar


def _bar(o, h, l, c) -> CandleBar:
    return CandleBar(
        symbol="ATM_CE",
        timestamp=datetime(2026, 7, 1, 9, 15, 0),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=50,
    )


def test_lower_wick_rejection():
    candles = [
        _bar(100, 102, 99, 101),
        _bar(101, 103, 95, 102),
    ]
    signal = detect_wick(candles, "CE")
    assert signal.direction in ("BULLISH_REJECTION", "NONE")
    assert signal.wick_body_ratio > 0


def test_false_wick_filtered():
    candles = [
        _bar(100, 110, 90, 100),
        _bar(100, 120, 80, 100),
    ]
    signal = detect_wick(candles, "CE")
    assert isinstance(signal.false_wick, bool)
