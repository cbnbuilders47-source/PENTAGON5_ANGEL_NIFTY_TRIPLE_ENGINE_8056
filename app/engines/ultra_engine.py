"""Ultra Engine — momentum/breakout logic (no execution)."""

from __future__ import annotations

from app.engines.decision_logger import log_decision
from app.engines.state_machine import EngineStateMachine
from app.intelligence.time_rules import force_exit_required, new_entries_allowed
from app.intelligence.types import EngineDecisionSnapshot, TradingContext
from app.intelligence.ultra_signals import analyze_ultra
from app.models.enums import EnginePhase, UltraDecision


class UltraEngine:
    NAME = "ultra"

    def __init__(self) -> None:
        self._sm = EngineStateMachine()
        self.last_snapshot: EngineDecisionSnapshot | None = None

    @property
    def phase(self) -> EnginePhase:
        return self._sm.phase

    def evaluate(self, ctx: TradingContext, allocated_margin: float, has_live_position: bool = False) -> EngineDecisionSnapshot:
        if not ctx.broker_connected:
            return self._finalize(UltraDecision.WAIT.value, ["Broker not connected"], ctx, None)

        if force_exit_required(ctx.session_phase) and has_live_position:
            return self._finalize(UltraDecision.WOULD_EXIT.value, ["Force exit window"], ctx, None)

        if not new_entries_allowed(ctx.session_phase) and not has_live_position:
            return self._finalize(UltraDecision.WAIT.value, ["Outside trading window"], ctx, None)

        if allocated_margin <= 0:
            return self._finalize(UltraDecision.WAIT.value, ["Insufficient margin"], ctx, None)

        premium = ctx.atm_ce_candles if ctx.bias_direction.value == "BULL" else ctx.atm_pe_candles
        if not premium:
            premium = ctx.atm_ce_candles or ctx.atm_pe_candles

        signal = analyze_ultra(ctx.nifty_candles, premium)

        if has_live_position:
            return self._finalize(UltraDecision.WAIT.value, signal.reasons + ["Holding position — monitoring exit"], ctx, signal)

        if signal.opportunity_rank < 65:
            return self._finalize(
                UltraDecision.WAIT.value,
                signal.reasons + ["Opportunity rank below threshold"],
                ctx,
                signal,
            )

        if signal.early_reversal and not signal.breakout:
            return self._finalize(UltraDecision.WAIT.value, signal.reasons + ["Reversal risk"], ctx, signal)

        if signal.momentum_strength >= 65 and (signal.breakout or signal.trend_continuation):
            self._sm.advance_for_decision(UltraDecision.WOULD_BUY.value)
            return self._finalize(UltraDecision.WOULD_BUY.value, signal.reasons, ctx, signal)

        self._sm.advance_for_decision(UltraDecision.READY.value)
        return self._finalize(UltraDecision.READY.value, signal.reasons + ["Monitoring momentum"], ctx, signal)

    def _finalize(
        self,
        decision: str,
        reasons: list[str],
        ctx: TradingContext,
        signal,
    ) -> EngineDecisionSnapshot:
        ltp = ctx.nifty_candles[-1].close if ctx.nifty_candles else 0.0
        confidence = signal.opportunity_rank if signal else 0.0
        snap = EngineDecisionSnapshot(
            engine=self.NAME,
            phase=self._sm.phase,
            decision=decision,
            reasons=reasons,
            confidence=confidence,
            opportunity_score=signal.opportunity_rank if signal else 0.0,
            entry_quality=signal.momentum_strength if signal else 0.0,
            momentum=signal.momentum_strength if signal else 0.0,
            liquidity=signal.market_speed if signal else 0.0,
            market_health=signal.premium_acceleration if signal else 0.0,
            expected_target=round(ltp * (1 + (signal.dynamic_target_pct / 100)), 2) if signal and ltp else None,
            expected_sl=round(ltp * 0.994, 2) if ltp else None,
            trailing_sl=round(ltp * (1 - signal.profit_lock_pct / 100), 2) if signal and ltp else None,
            updated_at=ctx.now,
        )
        self.last_snapshot = snap
        log_decision(snap)
        return snap

    def reset(self) -> None:
        self._sm.reset()
