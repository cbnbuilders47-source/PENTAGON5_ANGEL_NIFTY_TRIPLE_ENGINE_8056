"""Wick rejection detection for ATM CE/PE candles."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.schemas import CandleBar


@dataclass
class WickSignal:
    detected: bool
    direction: str  # BULLISH_REJECTION | BEARISH_REJECTION | NONE
    wick_body_ratio: float
    premium_recovery: bool
    premium_slowdown: bool
    false_wick: bool
    multi_candle_confirmed: bool
    premium_momentum: float
    reasons: list[str]


def detect_wick(candles: list[CandleBar], option_type: str) -> WickSignal:
    reasons: list[str] = []
    if len(candles) < 2:
        return WickSignal(False, "NONE", 0.0, False, False, False, False, 0.0, ["Insufficient candles"])

    c = candles[-1]
    body = abs(c.close - c.open) or 0.01
    upper_wick = c.high - max(c.open, c.close)
    lower_wick = min(c.open, c.close) - c.low
    wick_body_ratio = max(upper_wick, lower_wick) / body

    bullish_rejection = lower_wick > upper_wick * 1.5 and lower_wick / body >= 1.2
    bearish_rejection = upper_wick > lower_wick * 1.5 and upper_wick / body >= 1.2

    prev = candles[-2]
    premium_recovery = c.close > prev.close if bullish_rejection else c.close < prev.close if bearish_rejection else False
    premium_slowdown = abs(c.close - prev.close) < body * 0.5

    false_wick = wick_body_ratio > 4.0 and not premium_recovery
    multi_confirmed = _multi_candle_confirm(candles, bullish_rejection, bearish_rejection)
    prem_momentum = _premium_momentum(candles)

    direction = "NONE"
    if bullish_rejection and option_type == "CE":
        direction = "BULLISH_REJECTION"
        reasons.append("Lower wick rejection on CE")
    elif bearish_rejection and option_type == "PE":
        direction = "BEARISH_REJECTION"
        reasons.append("Upper wick rejection on PE")
    elif bullish_rejection:
        direction = "BULLISH_REJECTION"
        reasons.append("Lower wick rejection")
    elif bearish_rejection:
        direction = "BEARISH_REJECTION"
        reasons.append("Upper wick rejection")

    if wick_body_ratio >= 1.0:
        reasons.append(f"Wick/body ratio {wick_body_ratio:.1f}")
    if premium_recovery:
        reasons.append("Premium recovery")
    if premium_slowdown:
        reasons.append("Premium slowdown")
    if false_wick:
        reasons.append("False wick rejected")
    if multi_confirmed:
        reasons.append("Multi-candle confirmation")

    detected = (
        (bullish_rejection or bearish_rejection)
        and not false_wick
        and wick_body_ratio >= 0.8
    )

    return WickSignal(
        detected=detected,
        direction=direction,
        wick_body_ratio=round(wick_body_ratio, 2),
        premium_recovery=premium_recovery,
        premium_slowdown=premium_slowdown,
        false_wick=false_wick,
        multi_candle_confirmed=multi_confirmed,
        premium_momentum=prem_momentum,
        reasons=reasons,
    )


def _multi_candle_confirm(candles: list[CandleBar], bullish: bool, bearish: bool) -> bool:
    if len(candles) < 3:
        return False
    last3 = candles[-3:]
    if bullish:
        return last3[-1].low >= last3[-2].low and last3[-1].close > last3[-2].open
    if bearish:
        return last3[-1].high <= last3[-2].high and last3[-1].close < last3[-2].open
    return False


def _premium_momentum(candles: list[CandleBar]) -> float:
    if len(candles) < 4:
        return 0.0
    changes = [candles[i].close - candles[i - 1].close for i in range(-3, 0)]
    direction = sum(1 for x in changes if x > 0) - sum(1 for x in changes if x < 0)
    return min(100.0, max(0.0, 50.0 + direction * 15))
