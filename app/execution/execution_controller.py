"""Central execution controller — sole path to live orders."""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timedelta

from app.broker.margin_manager import MarginManager
from app.broker.order_manager import OrderManager
from app.broker.position_manager import PositionManager
from app.broker.readiness import BrokerReadinessGate
from app.core.clock import trading_now
from app.core.logging import get_logger
from app.core.state import AppState
from app.execution.execution_audit import ExecutionAudit
from app.execution.execution_models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionSignal,
    PendingManualApproval,
)
from app.execution.order_lifecycle import OrderLifecycle
from app.execution.quantity import calculate_lots
from app.intelligence.time_rules import engine_new_entries_allowed, special_no_entry_block_message
from app.models.enums import EngineOperatingMode, EngineStatus, ExecutionState, ExitReason
from app.risk.locks import TradingLocks
from app.risk.risk_manager import RiskManager
from app.scheduler.session_scheduler import SessionScheduler
from app.validation.manual_tracker import ManualValidationTracker
from app.validation.validation_service import ProductionValidationService
from app.storage.position_store import PositionStore

logger = get_logger(__name__)

MANUAL_APPROVAL_TTL_SEC = 60


class ExecutionController:
    """Engines must never call OrderManager directly."""

    def __init__(
        self,
        state: AppState,
        risk_manager: RiskManager,
        locks: TradingLocks,
        scheduler: SessionScheduler,
        readiness_gate: BrokerReadinessGate,
        order_manager: OrderManager,
        position_manager: PositionManager,
        manual_tracker: ManualValidationTracker | None = None,
        validation_service: ProductionValidationService | None = None,
        margin_manager: MarginManager | None = None,
        position_store: PositionStore | None = None,
    ) -> None:
        self._state = state
        self._risk = risk_manager
        self._locks = locks
        self._scheduler = scheduler
        self._readiness = readiness_gate
        self._orders = order_manager
        self._positions = position_manager
        self._audit = ExecutionAudit()
        self._pending_manual: dict[str, PendingManualApproval] = {}
        self._recent_results: list[ExecutionResult] = []
        self._manual = manual_tracker
        self._validation = validation_service
        self._margin = margin_manager
        self._position_store = position_store or PositionStore()
        self._exit_all_in_progress = False
        self._exiting_engines: set[str] = set()

    @property
    def pending_manual(self) -> dict[str, PendingManualApproval]:
        self._expire_manual_approvals()
        return self._pending_manual

    def get_engine_mode(self, engine: str) -> EngineOperatingMode:
        return self._state.get_engine_mode(engine)

    def set_engine_mode(self, engine: str, mode: EngineOperatingMode) -> str | None:
        if mode == EngineOperatingMode.AUTO and self._validation:
            gate = self._validation.check_auto_allowed(engine)
            if not gate.allowed:
                logger.warning("AUTO blocked for %s: %s", engine, gate.reason)
                return gate.reason
        previous = self.get_engine_mode(engine)
        self._state.set_engine_mode(engine, mode)
        logger.info("Engine %s mode changed %s → %s", engine, previous.value, mode.value)
        return None

    async def process_signal(self, signal: ExecutionSignal) -> ExecutionResult:
        request_id = str(uuid.uuid4())[:12]
        lifecycle = OrderLifecycle()
        lifecycle.transition(ExecutionState.SIGNAL_RECEIVED)
        lifecycle.transition(ExecutionState.GATE_CHECKING)

        mode = self.get_engine_mode(signal.engine)
        self._audit.log("signal_received", {"request_id": request_id, "engine": signal.engine, "action": signal.action, "mode": mode.value})

        block = self._check_gates(signal, mode, lifecycle)
        if block:
            result = ExecutionResult(request_id=request_id, engine=signal.engine, state=lifecycle.state, message=block)
            self._record(result)
            return result

        lots, qty = calculate_lots(
            self._state.engines[signal.engine].allocated_margin,
            signal.premium,
            self._state.available_margin,
            max_lots=self._state.auto_validation_max_lots.get(signal.engine) if mode == EngineOperatingMode.AUTO else None,
        )
        if qty <= 0:
            lifecycle.transition(ExecutionState.BLOCKED_BY_MARGIN)
            result = ExecutionResult(request_id=request_id, engine=signal.engine, state=lifecycle.state, message="Insufficient margin for lot")
            self._record(result)
            return result

        if mode == EngineOperatingMode.MONITOR:
            lifecycle.transition(ExecutionState.BLOCKED_BY_ENGINE_MODE)
            result = ExecutionResult(
                request_id=request_id,
                engine=signal.engine,
                state=lifecycle.state,
                message=f"MONITOR mode — would {signal.action}",
                quantity=qty,
            )
            self._record(result)
            return result

        if mode == EngineOperatingMode.MANUAL:
            if signal.action.startswith("BUY"):
                self._track_manual(signal.engine, "buy_signal_generated")
            approval = PendingManualApproval(
                approval_id=request_id,
                engine=signal.engine,
                action=signal.action,
                signal=signal,
                lots=lots,
                quantity=qty,
                expires_at=datetime.now() + timedelta(seconds=MANUAL_APPROVAL_TTL_SEC),
            )
            self._pending_manual[request_id] = approval
            self._state.set_pending_approval(approval.to_dict())
            if signal.action.startswith("BUY"):
                self._track_manual(signal.engine, "manual_approval_shown")
            lifecycle.transition(ExecutionState.BLOCKED_BY_ENGINE_MODE)
            result = ExecutionResult(request_id=request_id, engine=signal.engine, state=lifecycle.state, message="Awaiting manual approval", quantity=qty)
            self._record(result)
            return result

        if mode == EngineOperatingMode.AUTO:
            lifecycle.transition(ExecutionState.APPROVED)
            return await self._execute_live(request_id, signal, lifecycle, lots, qty)

        lifecycle.transition(ExecutionState.BLOCKED_BY_ENGINE_MODE)
        result = ExecutionResult(request_id=request_id, engine=signal.engine, state=lifecycle.state, message="Engine OFF")
        self._record(result)
        return result

    async def approve_manual(self, approval_id: str) -> ExecutionResult:
        self._expire_manual_approvals()
        approval = self._pending_manual.pop(approval_id, None)
        if not approval:
            return ExecutionResult(approval_id, "", ExecutionState.BLOCKED_BY_ENGINE_MODE, "Approval not found or expired")
        lifecycle = OrderLifecycle()
        lifecycle.transition(ExecutionState.SIGNAL_RECEIVED)
        lifecycle.transition(ExecutionState.GATE_CHECKING)
        block = self._check_gates(approval.signal, EngineOperatingMode.MANUAL, lifecycle, skip_duplicate=True)
        if block:
            return ExecutionResult(approval_id, approval.engine, lifecycle.state, block)
        self._track_manual(approval.engine, "user_approval_received")
        lifecycle.transition(ExecutionState.APPROVED)
        return await self._execute_live(approval_id, approval.signal, lifecycle, approval.lots, approval.quantity)

    async def reject_manual(self, approval_id: str) -> ExecutionResult:
        self._pending_manual.pop(approval_id, None)
        self._state.clear_pending_approval(approval_id)
        return ExecutionResult(approval_id, "", ExecutionState.COMPLETED, "Manual signal rejected")

    async def exit_all(self, reason: ExitReason = ExitReason.FORCE_EXIT) -> list[ExecutionResult]:
        if self._exit_all_in_progress or not self._state.live_positions:
            return []
        self._exit_all_in_progress = True
        try:
            results = []
            for engine, pos in list(self._state.live_positions.items()):
                if engine in self._exiting_engines:
                    continue
                signal = ExecutionSignal(
                    engine=engine,
                    action="EXIT",
                    symbol=pos.get("option_side", "CE"),
                    tradingsymbol=pos["tradingsymbol"],
                    token=pos["token"],
                    exchange=pos.get("exchange", "NFO"),
                    reasons=[reason.value],
                )
                results.append(await self._execute_exit(str(uuid.uuid4())[:12], signal, pos))
            return results
        finally:
            self._exit_all_in_progress = False

    async def exit_engine(self, engine: str, reason: ExitReason = ExitReason.MANUAL) -> ExecutionResult | None:
        pos = self._state.live_positions.get(engine)
        if not pos:
            return ExecutionResult(str(uuid.uuid4())[:12], engine, ExecutionState.COMPLETED, "No open position")
        if engine in self._exiting_engines:
            return ExecutionResult(str(uuid.uuid4())[:12], engine, ExecutionState.COMPLETED, "Exit already in progress")
        self._exiting_engines.add(engine)
        try:
            mode = self.get_engine_mode(engine)
            if mode == EngineOperatingMode.MANUAL:
                self._track_manual(engine, "exit_signal_generated")
                self._track_manual(engine, "manual_exit_approval_received")
            signal = ExecutionSignal(
                engine=engine, action="EXIT", symbol=pos.get("option_side", ""),
                tradingsymbol=pos["tradingsymbol"], token=pos["token"],
                exchange=pos.get("exchange", "NFO"), reasons=[reason.value],
            )
            return await self._execute_exit(str(uuid.uuid4())[:12], signal, pos)
        finally:
            self._exiting_engines.discard(engine)

    def status(self) -> dict:
        self._expire_manual_approvals()
        return {
            "recent": [r.to_dict() for r in self._recent_results[-20:]],
            "pending_manual": [a.to_dict() for a in self._pending_manual.values()],
            "live_positions": dict(self._state.live_positions),
            "engine_modes": self._state.engine_modes,
        }

    def _check_gates(self, signal: ExecutionSignal, mode: EngineOperatingMode, lifecycle: OrderLifecycle, skip_duplicate: bool = False) -> str | None:
        if mode == EngineOperatingMode.OFF:
            lifecycle.transition(ExecutionState.BLOCKED_BY_ENGINE_MODE)
            return "Engine OFF"

        if self._locks.kill_switch_active:
            lifecycle.transition(ExecutionState.BLOCKED_BY_RISK)
            return "Kill switch active"

        if signal.action.startswith("BUY") and signal.engine in self._state.live_positions:
            lifecycle.transition(ExecutionState.BLOCKED_BY_RISK)
            return f"Engine {signal.engine} already has open position"

        if self._state.force_exit_active and signal.action.startswith("BUY"):
            lifecycle.transition(ExecutionState.BLOCKED_BY_TIME)
            return "Force-exit window — entries blocked"

        now = trading_now()
        if signal.action.startswith("BUY") and not engine_new_entries_allowed(signal.engine, now):
            lifecycle.transition(ExecutionState.BLOCKED_BY_TIME)
            block_msg = special_no_entry_block_message(signal.engine, now)
            return block_msg or "New entries blocked by session schedule"

        sig_hash = hashlib.md5(f"{signal.engine}|{signal.action}|{signal.token}".encode()).hexdigest()
        hash_arg = None if skip_duplicate else (sig_hash if signal.action.startswith("BUY") else None)
        allowed, reason = self._risk.can_open_position(signal.engine, signal.tradingsymbol, hash_arg)
        if not allowed and signal.action.startswith("BUY"):
            lifecycle.transition(ExecutionState.BLOCKED_BY_RISK)
            return reason

        if mode == EngineOperatingMode.AUTO or (mode == EngineOperatingMode.MANUAL and signal.action == "EXIT"):
            report = self._readiness.evaluate()
            if not report.ready and signal.action.startswith("BUY"):
                lifecycle.transition(ExecutionState.BLOCKED_BY_BROKER)
                return "Broker not ready"

        if self._state.broker_reconnect_required and signal.action.startswith("BUY"):
            lifecycle.transition(ExecutionState.BLOCKED_BY_BROKER)
            return "Broker reconnect required"

        return None

    async def _execute_live(
        self,
        request_id: str,
        signal: ExecutionSignal,
        lifecycle: OrderLifecycle,
        lots: int,
        qty: int,
    ) -> ExecutionResult:
        start = time.perf_counter()
        lifecycle.transition(ExecutionState.ORDER_SENT)
        is_buy = not (signal.action == "EXIT" or signal.action.startswith("EXIT"))
        if is_buy:
            self._track_manual(signal.engine, "angel_buy_order_sent")

        if signal.action == "EXIT" or signal.action.startswith("EXIT"):
            pos = self._state.live_positions.get(signal.engine)
            if not pos:
                return ExecutionResult(request_id, signal.engine, ExecutionState.COMPLETED, "No position to exit")
            return await self._execute_exit(request_id, signal, pos)

        side = "BUY"
        response = await self._orders.place_buy_order(
            tradingsymbol=signal.tradingsymbol,
            symboltoken=signal.token,
            exchange=signal.exchange,
            quantity=qty,
        )

        latency = (time.perf_counter() - start) * 1000
        if not response.get("success"):
            lifecycle.transition(ExecutionState.ORDER_REJECTED)
            result = ExecutionResult(
                request_id=request_id, engine=signal.engine, state=lifecycle.state,
                message=response.get("message", "Order rejected"),
                broker_response=response, latency_ms=latency,
            )
            self._record(result)
            return result

        order_id = str(response.get("order_id", ""))
        lifecycle.transition(ExecutionState.ORDER_PENDING)
        confirmed = await self._orders.confirm_order_execution(order_id)
        if not confirmed.get("success"):
            confirmed = await self._orders.reconcile_order_fill(order_id)
        if not confirmed.get("success"):
            if confirmed.get("reconciled"):
                lifecycle.transition(ExecutionState.ORDER_REJECTED)
                result = ExecutionResult(
                    request_id=request_id, engine=signal.engine, state=lifecycle.state,
                    message=confirmed.get("message", "Order rejected"), order_id=order_id,
                    broker_response=confirmed, latency_ms=latency,
                )
            else:
                lifecycle.transition(ExecutionState.UNKNOWN_ORDER_STATE)
                result = ExecutionResult(
                    request_id=request_id, engine=signal.engine, state=lifecycle.state,
                    message="Order state unknown — position not created", order_id=order_id,
                    broker_response=confirmed, latency_ms=latency,
                )
            self._record(result)
            return result

        lifecycle.transition(ExecutionState.ORDER_CONFIRMED)
        lifecycle.transition(ExecutionState.POSITION_ACTIVE)
        exec_price = float(confirmed.get("executed_price") or signal.premium)
        self._track_manual(signal.engine, "buy_order_confirmed")
        self._track_manual(signal.engine, "executed_price_captured")
        self._track_manual(signal.engine, "position_active")
        position = {
            "engine": signal.engine,
            "tradingsymbol": signal.tradingsymbol,
            "token": signal.token,
            "exchange": signal.exchange,
            "option_side": signal.option_side or "",
            "strike": signal.strike,
            "expiry": signal.expiry or "",
            "quantity": qty,
            "lots": lots,
            "entry_price": exec_price,
            "current_ltp": exec_price,
            "target": signal.target,
            "stop_loss": signal.stop_loss,
            "trailing_sl": signal.trailing_sl,
            "entry_order_id": order_id,
            "entry_at": datetime.now().isoformat(),
            "peak_profit": 0.0,
        }
        self._state.set_live_position(signal.engine, position)
        self._state.engines[signal.engine].open_positions = 1
        self._persist_positions()
        await self._refresh_margin()

        result = ExecutionResult(
            request_id=request_id, engine=signal.engine, state=lifecycle.state,
            message="Order confirmed", order_id=order_id, executed_price=exec_price,
            quantity=qty, latency_ms=latency, broker_response=confirmed,
        )
        self._record(result)
        return result

    async def _execute_exit(self, request_id: str, signal: ExecutionSignal, pos: dict) -> ExecutionResult:
        start = time.perf_counter()
        lifecycle = OrderLifecycle()
        lifecycle.transition(ExecutionState.EXIT_SIGNAL_RECEIVED)
        lifecycle.transition(ExecutionState.EXIT_ORDER_SENT)
        self._track_manual(signal.engine, "sell_order_sent")

        qty = int(pos.get("quantity", 0))
        response = await self._orders.place_sell_order(
            tradingsymbol=pos["tradingsymbol"],
            symboltoken=pos["token"],
            exchange=pos.get("exchange", "NFO"),
            quantity=qty,
        )
        latency = (time.perf_counter() - start) * 1000

        if not response.get("success"):
            result = ExecutionResult(request_id, signal.engine, ExecutionState.ORDER_REJECTED, response.get("message", "Exit rejected"), broker_response=response, latency_ms=latency)
            self._record(result)
            return result

        order_id = str(response.get("order_id", ""))
        confirmed = await self._orders.confirm_order_execution(order_id)
        if not confirmed.get("success"):
            confirmed = await self._orders.reconcile_order_fill(order_id)
        if not confirmed.get("success"):
            state = ExecutionState.ORDER_REJECTED if confirmed.get("reconciled") else ExecutionState.UNKNOWN_ORDER_STATE
            msg = confirmed.get("message", "Exit not confirmed — position retained")
            if state == ExecutionState.UNKNOWN_ORDER_STATE:
                msg = "Exit state unknown — position retained"
            result = ExecutionResult(
                request_id, signal.engine, state, msg,
                order_id=order_id, broker_response=confirmed, latency_ms=latency,
            )
            self._record(result)
            return result

        exit_price = float(confirmed.get("executed_price") or pos.get("current_ltp", 0))
        entry = float(pos.get("entry_price", 0))
        points = exit_price - entry
        pnl = points * qty

        self._state.clear_live_position(signal.engine)
        self._state.engines[signal.engine].open_positions = 0
        self._state.engines[signal.engine].pnl += pnl
        self._state.record_trade(signal.engine, pos, exit_price, order_id, pnl, signal.reasons[0] if signal.reasons else "EXIT")
        self._track_manual(signal.engine, "sell_order_confirmed")
        self._track_manual(signal.engine, "report_row_created")

        result = ExecutionResult(
            request_id=request_id, engine=signal.engine, state=ExecutionState.EXIT_CONFIRMED,
            message="Exit confirmed", order_id=order_id, executed_price=exit_price,
            quantity=qty, latency_ms=latency, broker_response=confirmed,
        )
        lifecycle.transition(ExecutionState.COMPLETED)
        self._reset_engine_after_exit(signal.engine)
        self._persist_positions()
        await self._refresh_margin()
        self._record(result)
        return result

    def on_position_ltp_updated(self, engine: str) -> None:
        if engine in self._state.live_positions:
            self._track_manual(engine, "ltp_updating")
            self._track_manual(engine, "pnl_updating")

    def _reset_engine_after_exit(self, engine: str) -> None:
        if engine in self._state.engines:
            self._state.engines[engine].open_positions = 0
            self._state.engines[engine].status = EngineStatus.IDLE
        logger.info("ENGINE RESET AFTER EXIT — %s", engine)

    def _track_manual(self, engine: str, step: str) -> None:
        if self._manual:
            self._manual.mark(engine, step)

    def _persist_positions(self) -> None:
        self._position_store.save(dict(self._state.live_positions))

    async def _refresh_margin(self) -> None:
        if self._margin:
            try:
                await self._margin.refresh()
            except Exception as exc:
                logger.warning("Margin refresh after trade failed: %s", exc)

    def _record(self, result: ExecutionResult) -> None:
        self._recent_results.append(result)
        if len(self._recent_results) > 100:
            self._recent_results = self._recent_results[-100:]
        self._state.set_execution_result(result.to_dict())
        self._audit.log_result(result)
        self._track_manual(result.engine, "logs_created")

    def _expire_manual_approvals(self) -> None:
        now = datetime.now()
        expired = [k for k, v in self._pending_manual.items() if v.expires_at and v.expires_at < now]
        for k in expired:
            self._pending_manual.pop(k, None)
            self._state.clear_pending_approval(k)
