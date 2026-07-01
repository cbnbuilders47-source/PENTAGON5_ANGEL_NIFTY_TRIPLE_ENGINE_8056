"""Momentum and trend confirmation."""

from __future__ import annotations

from app.models.schemas import CandleBar


def momentum_score(candles: list[CandleBar], lookback: int = 8) -> float:
    if len(candles) < 3:
        return 0.0
    recent = candles[-lookback:]
    changes = [recent[i].close - recent[i - 1].close for i in range(1, len(recent))]
    if not changes:
        return 0.0
    avg = sum(changes) / len(changes)
    direction_strength = sum(1 for c in changes if (c > 0 and avg > 0) or (c < 0 and avg < 0))
    return min(100.0, (direction_strength / len(changes)) * 100)


def trend_confirmed(candles: list[CandleBar], bullish: bool) -> bool:
    if len(candles) < 5:
        return False
    recent = candles[-5:]
    highs = [c.high for c in recent]
    lows = [c.low for c in recent]
    if bullish:
        return highs[-1] >= max(highs[:-1]) and lows[-1] >= lows[0]
    return lows[-1] <= min(lows[:-1]) and highs[-1] <= highs[0]


def momentum_confirmed(candles: list[CandleBar], threshold: float = 55.0) -> bool:
    return momentum_score(candles) >= threshold
