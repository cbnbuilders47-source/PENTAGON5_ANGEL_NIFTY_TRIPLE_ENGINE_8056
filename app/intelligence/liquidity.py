"""Liquidity validation from candle volume."""

from __future__ import annotations

from app.models.schemas import CandleBar


def liquidity_score(candles: list[CandleBar], lookback: int = 10) -> float:
    if not candles:
        return 0.0
    recent = candles[-lookback:]
    volumes = [c.volume for c in recent if c.volume > 0]
    if not volumes:
        return 45.0
    avg = sum(volumes) / len(volumes)
    latest = recent[-1].volume or avg
    ratio = latest / avg if avg else 1.0
    return min(100.0, max(0.0, 40.0 + ratio * 30))


def liquidity_ok(candles: list[CandleBar], min_score: float = 50.0) -> bool:
    return liquidity_score(candles) >= min_score
