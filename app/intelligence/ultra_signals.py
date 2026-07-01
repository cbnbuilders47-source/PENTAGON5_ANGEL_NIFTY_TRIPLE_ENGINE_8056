"""Ultra engine momentum and breakout signals."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.schemas import CandleBar


@dataclass
class UltraSignal:
    momentum_strength: float
    premium_acceleration: float
    breakout: bool
    early_reversal: bool
    trend_continuation: bool
    market_speed: float
    dynamic_target_pct: float
    profit_lock_pct: float
    opportunity_rank: float
    reasons: list[str]


def analyze_ultra(nifty: list[CandleBar], premium: list[CandleBar]) -> UltraSignal:
    reasons: list[str] = []
    momentum_strength = _momentum_strength(nifty)
    acceleration = _premium_acceleration(premium)
    breakout = _breakout_detected(nifty)
    reversal = _early_reversal(nifty)
    continuation = momentum_strength > 65 and not reversal
    speed = _market_speed(nifty)

    if momentum_strength > 70:
        reasons.append("Momentum strength high")
    if acceleration > 60:
        reasons.append("Premium acceleration")
    if breakout:
        reasons.append("Breakout detected")
    if reversal:
        reasons.append("Early reversal detected")
    if continuation:
        reasons.append("Trend continuation")

    rank = min(100.0, (momentum_strength * 0.35) + (acceleration * 0.3) + (speed * 0.2) + (20 if breakout else 0))
    target_pct = 12.0 + (momentum_strength / 100) * 8.0
    lock_pct = 6.0 + (acceleration / 100) * 4.0

    return UltraSignal(
        momentum_strength=round(momentum_strength, 1),
        premium_acceleration=round(acceleration, 1),
        breakout=breakout,
        early_reversal=reversal,
        trend_continuation=continuation,
        market_speed=round(speed, 1),
        dynamic_target_pct=round(target_pct, 1),
        profit_lock_pct=round(lock_pct, 1),
        opportunity_rank=round(rank, 1),
        reasons=reasons,
    )


def _momentum_strength(candles: list[CandleBar]) -> float:
    if len(candles) < 5:
        return 0.0
    closes = [c.close for c in candles[-6:]]
    net = closes[-1] - closes[0]
    moves = sum(1 for i in range(1, len(closes)) if (closes[i] - closes[i - 1]) * net > 0)
    return min(100.0, (moves / (len(closes) - 1)) * 100)


def _premium_acceleration(candles: list[CandleBar]) -> float:
    if len(candles) < 4:
        return 0.0
    v1 = candles[-1].close - candles[-2].close
    v0 = candles[-2].close - candles[-3].close
    if v0 == 0:
        return 50.0
    accel = (v1 - v0) / abs(v0)
    return min(100.0, max(0.0, 50.0 + accel * 100))


def _breakout_detected(candles: list[CandleBar]) -> bool:
    if len(candles) < 8:
        return False
    recent = candles[-8:-1]
    c = candles[-1]
    return c.close > max(x.high for x in recent) or c.close < min(x.low for x in recent)


def _early_reversal(candles: list[CandleBar]) -> bool:
    if len(candles) < 5:
        return False
    a, b, c = candles[-3], candles[-2], candles[-1]
    return (a.close < b.close > c.close) or (a.close > b.close < c.close)


def _market_speed(candles: list[CandleBar]) -> float:
    if len(candles) < 4:
        return 0.0
    ranges = [c.high - c.low for c in candles[-5:]]
    avg = sum(ranges) / len(ranges)
    return min(100.0, avg * 2)
