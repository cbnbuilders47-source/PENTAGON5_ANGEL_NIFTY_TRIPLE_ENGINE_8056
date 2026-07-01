"""Bias engine tests."""

from datetime import datetime

from app.intelligence.bias import calculate_bias
from app.models.enums import BiasDirection
from app.models.schemas import CandleBar


def _candles(closes: list[float]) -> list[CandleBar]:
    return [
        CandleBar(
            symbol="NIFTY",
            timestamp=datetime(2026, 7, 1, 9, 15, i),
            open=c,
            high=c + 5,
            low=c - 5,
            close=c,
            volume=100,
        )
        for i, c in enumerate(closes)
    ]


def test_bullish_bias():
    direction, confidence = calculate_bias(_candles([100, 101, 102, 103, 104, 105, 106, 107]))
    assert direction == BiasDirection.BULL
    assert confidence > 50


def test_bearish_bias():
    direction, confidence = calculate_bias(_candles([107, 106, 105, 104, 103, 102, 101, 100]))
    assert direction == BiasDirection.BEAR
    assert confidence > 50


def test_neutral_insufficient_data():
    direction, confidence = calculate_bias(_candles([100, 101]))
    assert direction == BiasDirection.NEUTRAL
    assert confidence == 0.0
