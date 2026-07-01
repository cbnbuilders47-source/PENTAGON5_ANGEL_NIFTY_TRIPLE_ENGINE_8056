"""Opportunity and entry quality scoring."""

from __future__ import annotations

from app.intelligence.types import AnalysisMetrics


def entry_quality_score(
    bias_confidence: float,
    momentum: float,
    liquidity: float,
    market_health: float,
    trend_confirmed: bool,
) -> float:
    base = (bias_confidence * 0.3) + (momentum * 0.25) + (liquidity * 0.2) + (market_health * 0.25)
    if trend_confirmed:
        base += 8.0
    return min(100.0, round(base, 1))


def opportunity_score(metrics: AnalysisMetrics, bias_confidence: float) -> float:
    score = (
        bias_confidence * 0.25
        + metrics.momentum * 0.25
        + metrics.liquidity * 0.15
        + metrics.market_health * 0.2
        + metrics.entry_quality * 0.15
    )
    if metrics.trend_confirmed and metrics.momentum_confirmed:
        score += 10.0
    return min(100.0, round(score, 1))


def market_health_score(nifty: list, ce: list, pe: list) -> float:
    from app.intelligence.liquidity import liquidity_score
    from app.intelligence.momentum import momentum_score

    n = momentum_score(nifty) if nifty else 0.0
    l = max(liquidity_score(ce), liquidity_score(pe)) if (ce or pe) else 50.0
    return round((n * 0.5) + (l * 0.5), 1)
