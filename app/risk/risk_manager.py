"""Portfolio risk gates — LIVE ONLY, no order placement."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.broker.readiness import BrokerReadinessGate
from app.core.clock import trading_now
from app.core.logging import get_logger
from app.core.state import AppState
from app.intelligence.time_rules import engine_new_entries_allowed, special_no_entry_block_message
from app.risk.locks import TradingLocks
from app.scheduler.session_scheduler import SessionScheduler

logger = get_logger(__name__)


@dataclass
class RiskGate:
    name: str
    passed: bool
    message: str


@dataclass
class RiskStatus:
    trading_allowed: bool
    gates: list[RiskGate] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "trading_allowed": self.trading_allowed,
            "evaluated_at": self.evaluated_at.isoformat(),
            "gates": [{"name": g.name, "passed": g.passed, "message": g.message} for g in self.gates],
        }


class RiskManager:
    """Enforces all risk and safety gates before any live entry."""

    def __init__(
        self,
        state: AppState,
        locks: TradingLocks,
        scheduler: SessionScheduler,
        readiness_gate: BrokerReadinessGate | None = None,
    ) -> None:
        self._state = state
        self._locks = locks
        self._scheduler = scheduler
        self._readiness = readiness_gate
        self.last_status: RiskStatus | None = None

    def set_readiness_gate(self, gate: BrokerReadinessGate) -> None:
        self._readiness = gate

    def refresh_gates(self) -> RiskStatus:
        status = self.evaluate()
        self.last_status = status
        self._state.set_risk_status(status.to_dict())
        return status

    def evaluate(self) -> RiskStatus:
        gates = [
            self._gate_kill_switch(),
            self._gate_force_exit(),
            self._gate_new_entries(),
            self._gate_margin(),
            self._gate_allocation(),
            self._gate_broker_readiness(),
        ]
        trading_allowed = all(g.passed for g in gates)
        return RiskStatus(trading_allowed=trading_allowed, gates=gates)

    def can_open_position(self, engine: str, symbol: str, signal_hash: str | None = None) -> tuple[bool, str]:
        """Check all gates for a hypothetical entry. No orders placed."""
        if self._locks.kill_switch_active:
            return False, "Kill switch active"

        if self._state.force_exit_active:
            return False, "Force-exit window active"

        now = trading_now()
        if not engine_new_entries_allowed(engine, now):
            block_msg = special_no_entry_block_message(engine, now)
            if block_msg:
                return False, block_msg
            return False, "New entries not allowed in current session phase"

        if self._state.available_margin <= 0:
            return False, "No available margin"

        if not self._allocation_valid():
            return False, "Invalid engine allocation"

        if self._locks.is_engine_halted(engine):
            return False, f"Engine {engine} halted"

        if self._locks.is_symbol_halted(symbol):
            return False, f"Symbol {symbol} halted"

        if signal_hash and self._locks.is_duplicate_signal(signal_hash):
            return False, "Duplicate order signal blocked"

        if self._readiness:
            report = self._readiness.evaluate()
            if not report.ready:
                return False, "Broker readiness check failed"

        return True, "Risk gates passed (execution still disabled)"

    def should_force_exit(self) -> bool:
        return self._state.force_exit_active

    def _gate_kill_switch(self) -> RiskGate:
        ok = not self._locks.kill_switch_active
        return RiskGate("kill_switch", ok, "Kill switch off" if ok else "KILL SWITCH ACTIVE")

    def _gate_force_exit(self) -> RiskGate:
        ok = not self._state.force_exit_active
        return RiskGate("force_exit", ok, "No force exit" if ok else "Force-exit enforcement active")

    def _gate_new_entries(self) -> RiskGate:
        ok = self._state.new_entries_allowed
        return RiskGate("new_entries", ok, "Entries allowed" if ok else "Stop-new-entry enforced")

    def _gate_margin(self) -> RiskGate:
        ok = self._state.available_margin > 0 or not self._state.broker_connected
        return RiskGate("margin_available", ok, "Margin OK" if ok else "Margin unavailable")

    def _gate_allocation(self) -> RiskGate:
        ok = self._allocation_valid()
        return RiskGate("allocation_valid", ok, "Allocation 100%" if ok else "Allocation invalid")

    def _gate_broker_readiness(self) -> RiskGate:
        if not self._state.broker_connected:
            return RiskGate("broker_readiness", True, "Broker not connected — gate skipped")
        if not self._readiness:
            return RiskGate("broker_readiness", False, "Readiness gate not configured")
        report = self._readiness.evaluate()
        return RiskGate(
            "broker_readiness",
            report.ready,
            "Broker ready" if report.ready else "Broker not ready",
        )

    def _allocation_valid(self) -> bool:
        alloc = self._state.allocations
        total = sum(alloc.values())
        return abs(total - 100.0) < 0.01
