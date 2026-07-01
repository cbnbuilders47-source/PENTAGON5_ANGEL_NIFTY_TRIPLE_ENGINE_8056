"""Wick Engine — ATM CE/PE wick rejection logic (no execution)."""

from __future__ import annotations

from app.engines.decision_logger import log_decision
from app.engines.state_machine import EngineStateMachine
from app.intelligence.time_rules import force_exit_required, new_entries_allowed
from app.intelligence.types import EngineDecisionSnapshot, TradingContext
from app.intelligence.wick import detect_wick
from app.models.enums import EnginePhase, WickDecision


class WickEngine:
    NAME = "wick"

    def __init__(self) -> None:
        self._sm = EngineStateMachine()
        self._virtual_position: bool = False
        self.last_snapshot: EngineDecisionSnapshot | None = None

    @property
    def phase(self) -> EnginePhase:
        return self._sm.phase

    def evaluate(self, ctx: TradingContext, allocated_margin: float) -> EngineDecisionSnapshot:
        reasons: list[str] = []

        if not ctx.broker_connected:
            return self._finalize(WickDecision.WAIT.value, ["Broker not connected"], ctx, 0.0, 0.0, 0.0)

        if force_exit_required(ctx.session_phase) and self._virtual_position:
            snap = self._finalize(WickDecision.WOULD_EXIT.value, ["Force exit window"], ctx, 0.0, 0.0, 0.0)
            self._virtual_position = False
            self._sm.advance_for_decision(WickDecision.WOULD_EXIT.value, has_position=True)
            return snap

        if not new_entries_allowed(ctx.session_phase) and not self._virtual_position:
            return self._finalize(WickDecision.WAIT.value, ["Outside trading window"], ctx, 0.0, 0.0, 0.0)

        if allocated_margin <= 0:
            return self._finalize(WickDecision.WAIT.value, ["Insufficient margin"], ctx, 0.0, 0.0, 0.0)

        ce_signal = detect_wick(ctx.atm_ce_candles, "CE")
        pe_signal = detect_wick(ctx.atm_pe_candles, "PE")

        confidence = max(ce_signal.premium_momentum, pe_signal.premium_momentum)
        opportunity = 0.0
        entry_quality = 0.0

        if self._virtual_position:
            snap = self._finalize(WickDecision.WOULD_EXIT.value, ["Premium slowdown exit"], ctx, confidence, opportunity, entry_quality)
            self._virtual_position = False
            return snap

        active = ce_signal if ce_signal.detected else pe_signal if pe_signal.detected else None
        if not active:
            return self._finalize(
                WickDecision.WAIT.value,
                ["Scanning for wick rejection"] + ce_signal.reasons[:1],
                ctx,
                confidence,
                opportunity,
                entry_quality,
            )

        reasons.extend(active.reasons)
        opportunity = min(100.0, active.wick_body_ratio * 20 + active.premium_momentum * 0.5)
        entry_quality = opportunity * 0.9

        if active.false_wick:
            return self._finalize(WickDecision.WAIT.value, reasons + ["False wick"], ctx, confidence, opportunity, entry_quality)

        if not active.multi_candle_confirmed:
            self._sm.advance_for_decision(WickDecision.READY.value)
            return self._finalize(WickDecision.READY.value, reasons + ["Waiting confirmation"], ctx, confidence, opportunity, entry_quality)

        decision = WickDecision.WOULD_BUY.value
        self._virtual_position = True
        self._sm.advance_for_decision(decision, has_position=False)
        return self._finalize(decision, reasons, ctx, confidence, opportunity, entry_quality)

    def _finalize(
        self,
        decision: str,
        reasons: list[str],
        ctx: TradingContext,
        confidence: float,
        opportunity: float,
        entry_quality: float,
    ) -> EngineDecisionSnapshot:
        premium = ctx.atm_ce_candles[-1].close if ctx.atm_ce_candles else 0.0
        snap = EngineDecisionSnapshot(
            engine=self.NAME,
            phase=self._sm.phase,
            decision=decision,
            reasons=reasons,
            confidence=confidence,
            opportunity_score=opportunity,
            entry_quality=entry_quality,
            momentum=confidence,
            liquidity=50.0,
            market_health=50.0,
            expected_target=round(premium * 1.1, 2) if premium else None,
            expected_sl=round(premium * 0.92, 2) if premium else None,
            trailing_sl=round(premium * 0.95, 2) if premium else None,
            updated_at=ctx.now,
        )
        self.last_snapshot = snap
        log_decision(snap)
        return snap

    def reset(self) -> None:
        self._sm.reset()
        self._virtual_position = False
