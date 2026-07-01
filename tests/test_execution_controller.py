"""Execution controller gate and mode tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.state import AppState
from app.execution.execution_controller import ExecutionController
from app.execution.execution_models import ExecutionSignal
from app.models.enums import EngineOperatingMode, ExecutionState, ExitReason
from app.risk.locks import TradingLocks
from app.risk.risk_manager import RiskManager
from app.scheduler.session_scheduler import SessionScheduler


def _make_controller(state: AppState | None = None) -> ExecutionController:
    state = state or AppState()
    state.set_available_margin(100000)
    locks = TradingLocks()
    scheduler = SessionScheduler()
    scheduler._new_entries_allowed = True
    scheduler._force_exit_active = False
    readiness = MagicMock()
    readiness.evaluate.return_value = MagicMock(ready=True, to_dict=lambda: {"ready": True})
    orders = AsyncMock()
    orders.place_buy_order.return_value = {"success": True, "order_id": "O1"}
    orders.confirm_order_execution.return_value = {"success": True, "executed_price": 100.0}
    positions = AsyncMock()
    risk = RiskManager(state=state, locks=locks, scheduler=scheduler, readiness_gate=readiness)
    return ExecutionController(state, risk, locks, scheduler, readiness, orders, positions)


def _signal(action: str = "BUY_CE") -> ExecutionSignal:
    return ExecutionSignal(
        engine="normal",
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
async def test_monitor_mode_blocks_order():
    ctrl = _make_controller()
    ctrl.set_engine_mode("normal", EngineOperatingMode.MONITOR)
    result = await ctrl.process_signal(_signal())
    assert result.state == ExecutionState.BLOCKED_BY_ENGINE_MODE
    assert "MONITOR" in result.message


@pytest.mark.asyncio
async def test_off_mode_blocks():
    ctrl = _make_controller()
    ctrl.set_engine_mode("normal", EngineOperatingMode.OFF)
    result = await ctrl.process_signal(_signal())
    assert result.state == ExecutionState.BLOCKED_BY_ENGINE_MODE


@pytest.mark.asyncio
async def test_manual_mode_creates_approval():
    ctrl = _make_controller()
    ctrl.set_engine_mode("normal", EngineOperatingMode.MANUAL)
    result = await ctrl.process_signal(_signal())
    assert "approval" in result.message.lower()
    assert len(ctrl.pending_manual) == 1


@pytest.mark.asyncio
async def test_kill_switch_blocks():
    state = AppState()
    state.set_available_margin(100000)
    ctrl = _make_controller(state)
    ctrl.set_engine_mode("normal", EngineOperatingMode.AUTO)
    ctrl._locks.activate_kill_switch()
    result = await ctrl.process_signal(_signal())
    assert result.state == ExecutionState.BLOCKED_BY_RISK


@pytest.mark.asyncio
async def test_manual_approve_flow():
    ctrl = _make_controller()
    ctrl.set_engine_mode("normal", EngineOperatingMode.MANUAL)
    sig_result = await ctrl.process_signal(_signal())
    approval_id = sig_result.request_id
    approved = await ctrl.approve_manual(approval_id)
    assert approved.state in (ExecutionState.ORDER_CONFIRMED, ExecutionState.POSITION_ACTIVE)


@pytest.mark.asyncio
async def test_manual_reject():
    ctrl = _make_controller()
    ctrl.set_engine_mode("normal", EngineOperatingMode.MANUAL)
    sig_result = await ctrl.process_signal(_signal())
    result = await ctrl.reject_manual(sig_result.request_id)
    assert result.state == ExecutionState.COMPLETED


@pytest.mark.asyncio
async def test_exit_all():
    state = AppState()
    state.set_live_position("normal", {
        "tradingsymbol": "NIFTY24900CE", "token": "1", "quantity": 65,
        "entry_price": 100, "option_side": "CE",
    })
    ctrl = _make_controller(state)
    ctrl._orders.place_sell_order = AsyncMock(return_value={"success": True, "order_id": "E1"})
    ctrl._orders.confirm_order_execution = AsyncMock(return_value={"success": True, "executed_price": 110.0})
    results = await ctrl.exit_all(ExitReason.FORCE_EXIT)
    assert len(results) == 1
