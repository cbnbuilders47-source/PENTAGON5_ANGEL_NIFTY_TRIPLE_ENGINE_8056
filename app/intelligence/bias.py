"""Bias calculation from NIFTY candles."""

from __future__ import annotations

from app.models.enums import BiasDirection
from app.models.schemas import CandleBar


def calculate_bias(candles: list[CandleBar]) -> tuple[BiasDirection, float]:
    """Derive bull/bear bias and confidence from recent NIFTY 1m candles."""
    if len(candles) < 5:
        return BiasDirection.NEUTRAL, 0.0

    recent = candles[-10:]
    closes = [c.close for c in recent]
    ups = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i - 1])
    downs = sum(1 for i in range(1, len(closes)) if closes[i] < closes[i - 1])
    total_moves = ups + downs or 1

    net_change = closes[-1] - closes[0]
    pct_change = (net_change / closes[0]) * 100 if closes[0] else 0.0

    if pct_change > 0.05 and ups >= downs:
        direction = BiasDirection.BULL
        confidence = min(100.0, 50.0 + (ups / total_moves) * 40 + abs(pct_change) * 10)
    elif pct_change < -0.05 and downs >= ups:
        direction = BiasDirection.BEAR
        confidence = min(100.0, 50.0 + (downs / total_moves) * 40 + abs(pct_change) * 10)
    else:
        direction = BiasDirection.NEUTRAL
        confidence = max(0.0, 30.0 - abs(pct_change) * 5)

    return direction, round(confidence, 1)
