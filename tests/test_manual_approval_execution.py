"""Regression tests for manual approval execution visibility and pending cleanup."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.broker.order_manager import OrderManager
from app.core.state import AppState
from app.execution.execution_controller import ExecutionController
from app.execution.execution_models import ExecutionSignal
from app.models.enums import EngineOperatingMode, ExecutionState
from app.risk.locks import TradingLocks
from app.risk.risk_manager import RiskManager
from app.scheduler.session_scheduler import SessionScheduler

TRADING_HOUR = datetime(2026, 7, 1, 10, 0, 0)


@pytest.fixture(autouse=True)
def trading_hours_clock():
    with (
        patch("app.execution.execution_controller.trading_now") as ctrl_now,
        patch("app.risk.risk_manager.trading_now") as risk_now,
    ):
        ctrl_now.return_value = TRADING_HOUR
        risk_now.return_value = TRADING_HOUR
        yield


def _make_controller(state: AppState | None = None, orders: AsyncMock | None = None) -> ExecutionController:
    state = state or AppState()
    state.set_available_margin(100000)
    locks = TradingLocks()
    scheduler = SessionScheduler()
    scheduler._new_entries_allowed = True
    scheduler._force_exit_active = False
    readiness = MagicMock()
    readiness.evaluate.return_value = MagicMock(ready=True, to_dict=lambda: {"ready": True})
    if orders is None:
        orders = AsyncMock()
        orders.place_buy_order.return_value = {"success": True, "order_id": "O1"}
        orders.confirm_order_execution.return_value = {"success": True, "executed_price": 100.0}
    positions = AsyncMock()
    risk = RiskManager(state=state, locks=locks, scheduler=scheduler, readiness_gate=readiness)
    return ExecutionController(state, risk, locks, scheduler, readiness, orders, positions)


def _signal(engine: str = "wick", action: str = "BUY_CE") -> ExecutionSignal:
    return ExecutionSignal(
        engine=engine,
        action=action,
        symbol="ATM_CE",
        tradingsymbol="NIFTY24900CE",
        token="12345",
        exchange="NFO",
        strike=24900,
        option_side="CE",
        premium=50.0,
        confidence=80.0,
    )


@pytest.mark.asyncio
async def test_empty_angel_response_order_rejected_and_audited():
    orders = AsyncMock()
    orders.place_buy_order.return_value = {"success": False, "message": "Empty response", "reason": "Angel placeOrder returned None"}
    ctrl = _make_controller(orders=orders)
    ctrl.set_engine_mode("wick", EngineOperatingMode.MANUAL)
    sig = await ctrl.process_signal(_signal())
    approval_id = sig.request_id
    assert approval_id in ctrl.pending_manual

    result = await ctrl.approve_manual(approval_id)
    assert result.state == ExecutionState.ORDER_REJECTED
    assert "Empty response" in result.message
    assert approval_id not in ctrl.pending_manual
    assert not any(a.get("approval_id") == approval_id for a in ctrl._state.pending_approvals)
    assert "wick" not in ctrl._state.live_positions
    assert any(r.request_id == approval_id and r.state == ExecutionState.ORDER_REJECTED for r in ctrl._recent_results)


@pytest.mark.asyncio
async def test_approval_consumed_removes_pending_card():
    ctrl = _make_controller()
    ctrl.set_engine_mode("wick", EngineOperatingMode.MANUAL)
    sig = await ctrl.process_signal(_signal())
    approval_id = sig.request_id
    assert len(ctrl._state.pending_approvals) == 1

    result = await ctrl.approve_manual(approval_id)
    assert result.state == ExecutionState.POSITION_ACTIVE
    assert approval_id not in ctrl.pending_manual
    assert ctrl._state.pending_approvals == []
    assert "wick" in ctrl._state.live_positions


@pytest.mark.asyncio
async def test_expired_approval_clear_error_and_audited():
    ctrl = _make_controller()
    ctrl.set_engine_mode("wick", EngineOperatingMode.MANUAL)
    sig = await ctrl.process_signal(_signal())
    approval_id = sig.request_id
    approval = ctrl.pending_manual[approval_id]
    approval.expires_at = datetime.now() - timedelta(seconds=1)

    result = await ctrl.approve_manual(approval_id)
    assert result.state == ExecutionState.BLOCKED_BY_ENGINE_MODE
    assert "not found or expired" in result.message.lower()
    assert approval_id not in ctrl.pending_manual
    assert not any(a.get("approval_id") == approval_id for a in ctrl._state.pending_approvals)
    assert any(r.request_id == approval_id for r in ctrl._recent_results)


@pytest.mark.asyncio
async def test_gate_blocked_audited_and_approval_retained():
    state = AppState()
    state.set_available_margin(100000)
    ctrl = _make_controller(state)
    ctrl.set_engine_mode("wick", EngineOperatingMode.MANUAL)
    sig = await ctrl.process_signal(_signal())
    approval_id = sig.request_id
    ctrl._locks.activate_kill_switch()

    result = await ctrl.approve_manual(approval_id)
    assert result.state == ExecutionState.BLOCKED_BY_RISK
    assert "kill switch" in result.message.lower()
    assert approval_id in ctrl.pending_manual
    assert any(r.request_id == approval_id and r.state == ExecutionState.BLOCKED_BY_RISK for r in ctrl._recent_results)


@pytest.mark.asyncio
async def test_get_pending_approvals_syncs_stale_state():
    ctrl = _make_controller()
    ctrl.set_engine_mode("wick", EngineOperatingMode.MANUAL)
    sig = await ctrl.process_signal(_signal())
    approval_id = sig.request_id
    ctrl._pending_manual.pop(approval_id)
    ctrl._state.pending_approvals.append({"approval_id": approval_id, "engine": "wick"})

    pending = ctrl.get_pending_approvals()
    assert pending == []
    assert ctrl._state.pending_approvals == []


def test_order_manager_describe_none_response():
    msg, reason = OrderManager._describe_order_failure(None)
    assert msg == "Empty response"
    assert "None" in reason


def test_order_manager_describe_empty_dict():
    msg, reason = OrderManager._describe_order_failure({})
    assert msg == "Empty response"
    assert "empty dict" in reason


def test_order_manager_parse_string_order_id():
    parsed = OrderManager._parse_place_order_response("240703000123456")
    assert parsed["success"] is True
    assert parsed["order_id"] == "240703000123456"


def test_order_manager_describe_status_false():
    msg, reason = OrderManager._describe_order_failure({"status": False, "message": "Invalid Token"})
    assert msg == "Invalid Token"
    assert "status=False" in reason
