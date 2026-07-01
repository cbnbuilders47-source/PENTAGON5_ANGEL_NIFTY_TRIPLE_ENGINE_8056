"""Market mode detector tests."""

from datetime import datetime

from app.intelligence.market_mode import detect_market_mode
from app.models.enums import MarketMode
from app.models.schemas import CandleBar


def _series(start: float, steps: list[float]) -> list[CandleBar]:
    prices = [start]
    for s in steps:
        prices.append(prices[-1] + s)
    return [
        CandleBar(
            symbol="NIFTY",
            timestamp=datetime(2026, 7, 1, 9, 15, min(i, 59)),
            open=p,
            high=p + 2,
            low=p - 2,
            close=p,
            volume=100,
        )
        for i, p in enumerate(prices)
    ]


def test_trending_mode():
    nifty = _series(22000, [5, 6, 5, 7, 6, 8, 7, 9, 8, 10, 9])
    mode = detect_market_mode(nifty, nifty, nifty)
    assert mode in (MarketMode.TRENDING, MarketMode.BREAKOUT, MarketMode.SLOW_TREND)


def test_range_mode():
    nifty = _series(22000, [2, -2, 2, -2, 2, -2, 2, -2, 2, -2, 2])
    mode = detect_market_mode(nifty, nifty, nifty)
    assert mode in (MarketMode.RANGE, MarketMode.REVERSAL, MarketMode.VOLATILE)
