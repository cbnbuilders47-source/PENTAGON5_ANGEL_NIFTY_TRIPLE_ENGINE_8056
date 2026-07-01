"""Production validation status and AUTO safety gates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.broker.readiness import BrokerReadinessGate
from app.core.constants import ENGINES
from app.core.state import AppState
from app.market.atm_manager import ATMManager
from app.market.candle_builder import CandleBuilder
from app.market.instrument_master import InstrumentMaster
from app.models.enums import EngineOperatingMode, SessionPhase
from app.scheduler.session_scheduler import SessionScheduler
from app.validation.manual_tracker import ManualValidationTracker

FRESHNESS_SEC = 120


@dataclass
class AutoGateResult:
    allowed: bool
    reason: str | None = None


class ProductionValidationService:
    """Formal MONITOR validation checklist and AUTO safety gate."""

    def __init__(
        self,
        state: AppState,
        readiness_gate: BrokerReadinessGate,
        candle_builder: CandleBuilder,
        atm_manager: ATMManager,
        instrument_master: InstrumentMaster,
        scheduler: SessionScheduler,
        manual_tracker: ManualValidationTracker,
    ) -> None:
        self._state = state
        self._readiness = readiness_gate
        self._candles = candle_builder
        self._atm = atm_manager
        self._instruments = instrument_master
        self._scheduler = scheduler
        self._manual = manual_tracker

    def evaluate_monitor_checks(self) -> list[dict]:
        report = self._readiness.evaluate()
        check_map = {c.name: c for c in report.checks}
        now = datetime.now()

        def rd(name: str, label: str) -> dict:
            c = check_map.get(name)
            if c:
                return {"name": name, "label": label, "passed": c.passed, "message": c.message}
            return {"name": name, "label": label, "passed": False, "message": "Not evaluated"}

        checks = [
            rd("angel_connected", "Angel Login"),
            rd("jwt_valid", "JWT Valid"),
            rd("feed_token_valid", "Feed Token Valid"),
            rd("websocket_connected", "WebSocket Stable"),
            rd("nifty_tick_fresh", "NIFTY Tick Fresh"),
            rd("atm_ce_tick_fresh", "ATM CE Tick Fresh"),
            rd("atm_pe_tick_fresh", "ATM PE Tick Fresh"),
            rd("margin_fetched", "Margin Fetched"),
            {
                "name": "atm_strike_resolved",
                "label": "ATM Strike Resolved",
                "passed": bool(self._atm.atm_strike),
                "message": f"ATM {self._atm.atm_strike}" if self._atm.atm_strike else "ATM not resolved",
            },
            rd("expiry_selected", "Expiry Selected"),
            {
                "name": "readiness_full",
                "label": "Readiness 11/11",
                "passed": report.ready,
                "message": f"{sum(1 for c in report.checks if c.passed)}/{len(report.checks)}",
            },
            {
                "name": "bull_bear_updating",
                "label": "Bull/Bear updating",
                "passed": self._state.bias_confidence_pct > 0 or self._state.bias_locked,
                "message": f"{self._state.bias_direction.value} {self._state.bias_confidence_pct:.0f}%",
            },
            {
                "name": "candle_builder_updating",
                "label": "Candle builder updating",
                "passed": self._feed_fresh("NIFTY", now),
                "message": self._feed_age_msg("NIFTY"),
            },
            {
                "name": "engine_decisions_updating",
                "label": "Engine decisions updating",
                "passed": self._decisions_fresh(now),
                "message": "Recent engine decisions" if self._decisions_fresh(now) else "No recent decisions",
            },
            {
                "name": "logs_updating",
                "label": "Logs updating",
                "passed": (now - self._state.last_updated).total_seconds() < FRESHNESS_SEC,
                "message": f"State updated {(now - self._state.last_updated).total_seconds():.0f}s ago",
            },
        ]
        return checks

    def status(self) -> dict:
        checks = self.evaluate_monitor_checks()
        missing = [c["label"] for c in checks if not c["passed"]]
        manual_ready = all(c["passed"] for c in checks)
        any_manual_passed = self._manual.any_passed()
        notes: list[str] = []

        if self._state.broker_reconnect_required:
            notes.append("Broker reconnect required — tokens/session invalid")
        if self._state.recovery_status.get("status") == "dirty":
            notes.append("Recovery check dirty — review open positions")
        if not any_manual_passed:
            notes.append("Complete manual validation cycle before AUTO")

        ready_auto = manual_ready and any_manual_passed
        if not any_manual_passed:
            ready_auto = False

        if manual_ready:
            self._state.mark_validation_success()

        return {
            "ready_for_manual_validation": manual_ready,
            "ready_for_auto_validation": ready_auto,
            "missing_checks": missing,
            "last_success_time": self._state.validation_last_success.isoformat() if self._state.validation_last_success else None,
            "validation_notes": notes,
            "checks": checks,
        }

    def manual_status(self) -> dict:
        return {
            "engines": self._manual.all_status(),
            "normal_manual_cycle_passed": self._manual.is_passed("normal"),
            "wick_manual_cycle_passed": self._manual.is_passed("wick"),
            "ultra_manual_cycle_passed": self._manual.is_passed("ultra"),
        }

    def auto_allowed_by_engine(self) -> dict[str, dict]:
        return {e: self.check_auto_allowed(e).__dict__ for e in ENGINES}

    def check_auto_allowed(self, engine: str) -> AutoGateResult:
        if engine not in ENGINES:
            return AutoGateResult(False, f"Unknown engine: {engine}")

        report = self._readiness.evaluate()
        if not report.ready:
            return AutoGateResult(False, "Broker readiness incomplete")

        if not self._manual.is_passed(engine):
            return AutoGateResult(False, "Manual validation not completed")

        recovery = self._state.recovery_status
        if recovery.get("status") == "dirty":
            return AutoGateResult(False, "Recovery check required")

        if self._state.kill_switch_active:
            return AutoGateResult(False, "Kill switch active")

        if not self._state.new_entries_allowed:
            return AutoGateResult(False, "Scheduler does not allow trading")

        if self._state.session_phase not in (SessionPhase.TRADING, SessionPhase.BIAS_LOCKED):
            if not self._state.live_positions.get(engine):
                return AutoGateResult(False, "Scheduler does not allow trading")

        if self._state.broker_reconnect_required:
            return AutoGateResult(False, "Broker reconnect required")

        pos = self._state.live_positions.get(engine)
        if pos and pos.get("unknown"):
            return AutoGateResult(False, "Recovery check required")

        return AutoGateResult(True, None)

    def operator_bundle(self) -> dict:
        return {
            "validation_status": self.status(),
            "manual_validation_status": self.manual_status(),
            "auto_allowed_by_engine": self.auto_allowed_by_engine(),
            "recovery_status": dict(self._state.recovery_status),
            "reconnect_status": dict(self._state.reconnect_status),
        }

    def _feed_fresh(self, symbol: str, now: datetime) -> bool:
        last = self._candles.get_last_tick_at(symbol)
        if not last:
            return False
        return (now - last).total_seconds() <= FRESHNESS_SEC

    def _feed_age_msg(self, symbol: str) -> str:
        last = self._candles.get_last_tick_at(symbol)
        if not last:
            return "No ticks"
        age = (datetime.now() - last).total_seconds()
        return f"Last tick {age:.0f}s ago"

    def _decisions_fresh(self, now: datetime) -> bool:
        for snap in self._state.engine_decisions.values():
            updated = snap.get("updated_at")
            if not updated:
                continue
            try:
                if (now - datetime.fromisoformat(updated)).total_seconds() <= FRESHNESS_SEC:
                    return True
            except ValueError:
                continue
        return False
