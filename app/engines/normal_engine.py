"""Normal Engine — bias-driven NIFTY options logic (no execution)."""

from __future__ import annotations

import hashlib

from app.engines.decision_logger import log_decision
from app.engines.state_machine import EngineStateMachine
from app.intelligence.liquidity import liquidity_ok, liquidity_score
from app.intelligence.momentum import momentum_confirmed, momentum_score, trend_confirmed
from app.intelligence.opportunity import entry_quality_score, market_health_score, opportunity_score
from app.intelligence.time_rules import force_exit_required, new_entries_allowed
from app.intelligence.types import AnalysisMetrics, EngineDecisionSnapshot, TradingContext
from app.models.enums import BiasDirection, EnginePhase, NormalDecision

MIN_OPPORTUNITY = 62.0
MIN_ENTRY_QUALITY = 58.0


class NormalEngine:
    NAME = "normal"

    def __init__(self) -> None:
        self._sm = EngineStateMachine()
        self._last_signal_hash: str | None = None
        self.last_snapshot: EngineDecisionSnapshot | None = None

    @property
    def phase(self) -> EnginePhase:
        return self._sm.phase

    def evaluate(self, ctx: TradingContext, allocated_margin: float, has_live_position: bool = False) -> EngineDecisionSnapshot:
        reasons: list[str] = []
        metrics = AnalysisMetrics()

        if not ctx.broker_connected:
            return self._finalize(NormalDecision.BLOCKED.value, reasons + ["Broker not connected"], ctx, metrics)

        if force_exit_required(ctx.session_phase):
            if has_live_position:
                reasons.append("Force exit window active")
                return self._finalize(NormalDecision.WOULD_EXIT.value, reasons, ctx, metrics)
            return self._finalize(NormalDecision.BLOCKED.value, reasons + ["Session force exit"], ctx, metrics)

        if not new_entries_allowed(ctx.session_phase) and not has_live_position:
            return self._finalize(NormalDecision.WAIT.value, reasons + ["Outside trading window"], ctx, metrics)

        if allocated_margin <= 0:
            return self._finalize(NormalDecision.BLOCKED.value, reasons + ["Insufficient allocated margin"], ctx, metrics)

        bullish = ctx.bias_direction == BiasDirection.BULL
        bearish = ctx.bias_direction == BiasDirection.BEAR

        metrics.momentum = momentum_score(ctx.nifty_candles)
        metrics.liquidity = max(liquidity_score(ctx.atm_ce_candles), liquidity_score(ctx.atm_pe_candles))
        metrics.market_health = market_health_score(ctx.nifty_candles, ctx.atm_ce_candles, ctx.atm_pe_candles)
        metrics.trend_confirmed = trend_confirmed(ctx.nifty_candles, bullish=bullish) or trend_confirmed(
            ctx.nifty_candles, bullish=False
        )
        metrics.momentum_confirmed = momentum_confirmed(ctx.nifty_candles)
        metrics.entry_quality = entry_quality_score(
            ctx.bias_confidence, metrics.momentum, metrics.liquidity, metrics.market_health, metrics.trend_confirmed
        )
        metrics.opportunity_score = opportunity_score(metrics, ctx.bias_confidence)

        reasons.append(f"Bias {ctx.bias_confidence:.0f}% {ctx.bias_direction.value}")
        if metrics.trend_confirmed:
            reasons.append("Trend confirmed")
        if metrics.momentum_confirmed:
            reasons.append("Momentum strong")
        if liquidity_ok(ctx.atm_ce_candles) or liquidity_ok(ctx.atm_pe_candles):
            reasons.append("Liquidity good")

        if has_live_position:
            reasons.append("Live position active — monitoring exit")
            return self._finalize(NormalDecision.WAIT.value, reasons, ctx, metrics)

        if ctx.bias_confidence < 55:
            return self._finalize(NormalDecision.WAIT.value, reasons + ["Waiting confirmation"], ctx, metrics)

        if metrics.opportunity_score < MIN_OPPORTUNITY or metrics.entry_quality < MIN_ENTRY_QUALITY:
            return self._finalize(NormalDecision.WAIT.value, reasons + ["Opportunity below threshold"], ctx, metrics)

        decision = NormalDecision.READY.value
        if bullish and metrics.trend_confirmed and metrics.momentum_confirmed:
            decision = NormalDecision.WOULD_BUY_CE.value
            reasons.append("CE entry criteria met")
        elif bearish and metrics.trend_confirmed and metrics.momentum_confirmed:
            decision = NormalDecision.WOULD_BUY_PE.value
            reasons.append("PE entry criteria met")
        elif metrics.opportunity_score >= MIN_OPPORTUNITY:
            decision = NormalDecision.READY.value
            reasons.append("Setup forming")

        if self._duplicate_blocked(decision, reasons):
            return self._finalize(NormalDecision.WAIT.value, reasons + ["Duplicate signal prevented"], ctx, metrics)

        snap = self._finalize(decision, reasons, ctx, metrics)
        self._sm.advance_for_decision(decision, has_position=has_live_position)
        return snap

    def _duplicate_blocked(self, decision: str, reasons: list[str]) -> bool:
        if not decision.startswith("WOULD_BUY"):
            return False
        payload = f"{decision}|{'|'.join(reasons)}"
        digest = hashlib.md5(payload.encode()).hexdigest()
        if digest == self._last_signal_hash:
            return True
        self._last_signal_hash = digest
        return False

    def _finalize(
        self,
        decision: str,
        reasons: list[str],
        ctx: TradingContext,
        metrics: AnalysisMetrics,
    ) -> EngineDecisionSnapshot:
        ltp = ctx.nifty_candles[-1].close if ctx.nifty_candles else 0.0
        target = round(ltp * 1.008, 2) if ltp else None
        sl = round(ltp * 0.996, 2) if ltp else None
        trailing = round(ltp * 0.997, 2) if ltp else None

        snap = EngineDecisionSnapshot(
            engine=self.NAME,
            phase=self._sm.phase,
            decision=decision,
            reasons=reasons,
            confidence=ctx.bias_confidence,
            opportunity_score=metrics.opportunity_score,
            entry_quality=metrics.entry_quality,
            momentum=metrics.momentum,
            liquidity=metrics.liquidity,
            market_health=metrics.market_health,
            expected_target=target,
            expected_sl=sl,
            trailing_sl=trailing,
            updated_at=ctx.now,
        )
        self.last_snapshot = snap
        log_decision(snap)
        return snap

    def reset(self) -> None:
        self._sm.reset()
        self._last_signal_hash = None
