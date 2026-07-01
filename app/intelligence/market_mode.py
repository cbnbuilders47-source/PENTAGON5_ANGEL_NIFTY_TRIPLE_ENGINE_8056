"""Market mode detection."""

from __future__ import annotations

from app.models.enums import MarketMode
from app.models.schemas import CandleBar


def detect_market_mode(nifty: list[CandleBar], ce: list[CandleBar], pe: list[CandleBar]) -> MarketMode:
    if len(nifty) < 8:
        return MarketMode.SLOW_TREND

    recent = nifty[-12:]
    closes = [c.close for c in recent]
    highs = [c.high for c in recent]
    lows = [c.low for c in recent]

    price_range = max(highs) - min(lows)
    avg_price = sum(closes) / len(closes)
    range_pct = (price_range / avg_price) * 100 if avg_price else 0.0

    net = closes[-1] - closes[0]
    net_pct = abs(net / closes[0]) * 100 if closes[0] else 0.0

    # Direction changes
    direction_changes = 0
    for i in range(2, len(closes)):
        prev = closes[i - 1] - closes[i - 2]
        curr = closes[i] - closes[i - 1]
        if prev * curr < 0:
            direction_changes += 1

    premium_vol = _premium_volatility(ce, pe)

    if range_pct > 0.35 and premium_vol > 0.25:
        return MarketMode.VOLATILE
    if net_pct > 0.2 and direction_changes <= 2:
        return MarketMode.TRENDING
    if net_pct > 0.12 and direction_changes <= 3:
        return MarketMode.BREAKOUT
    if direction_changes >= 5 and range_pct < 0.15:
        return MarketMode.RANGE
    if direction_changes >= 4 and abs(net) > price_range * 0.3:
        return MarketMode.REVERSAL
    if net_pct > 0.08:
        return MarketMode.SLOW_TREND
    return MarketMode.RANGE


def _premium_volatility(ce: list[CandleBar], pe: list[CandleBar]) -> float:
    series = ce[-8:] if len(ce) >= 8 else pe[-8:]
    if len(series) < 3:
        return 0.0
    closes = [c.close for c in series]
    return (max(closes) - min(closes)) / (sum(closes) / len(closes)) if closes else 0.0
