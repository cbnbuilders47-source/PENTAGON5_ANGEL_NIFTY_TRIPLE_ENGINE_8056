"""Opportunity score tests."""

from app.intelligence.opportunity import entry_quality_score, opportunity_score
from app.intelligence.types import AnalysisMetrics


def test_opportunity_score_boosted_by_confirmations():
    metrics = AnalysisMetrics(
        momentum=70,
        liquidity=65,
        market_health=60,
        entry_quality=65,
        trend_confirmed=True,
        momentum_confirmed=True,
    )
    score = opportunity_score(metrics, bias_confidence=75)
    assert score >= 70


def test_entry_quality_score():
    score = entry_quality_score(80, 70, 60, 65, trend_confirmed=True)
    assert score > 60
