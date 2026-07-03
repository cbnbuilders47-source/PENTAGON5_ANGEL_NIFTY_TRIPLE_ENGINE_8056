"""Duplicate signal guard — must not block AUTO after MONITOR signals."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import REAL_ORDER_ID, REAL_ORDER_ID_2, confirm_ok

from app.core.state import AppState
from app.execution.execution_controller import ExecutionController
from app.execution.execution_models import ExecutionSignal
from app.models.enums import EngineOperatingMode, ExecutionState, SessionPhase
from app.risk.locks import TradingLocks
from app.risk.risk_manager import RiskManager
from app.scheduler.session_scheduler import SessionScheduler
from app.validation.manual_tracker import ManualValidationTracker
from app.validation.validation_service import ProductionValidationService

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


def _ctrl(supervised_auto: bool = True) -> ExecutionController:
    state = AppState()
    state.set_available_margin(100000)
    state.supervised_auto_enabled = supervised_auto
    state.apply_scheduler_status(MagicMock(
        current_phase=SessionPhase.TRADING,
        bias_locked=True,
        new_entries_allowed=True,
        force_exit_active=False,
    ))
    state.set_recovery_status({"status": "clean", "clean": True, "message": "ok"})
    locks = TradingLocks()
    scheduler = SessionScheduler()
    scheduler._new_entries_allowed = True
    readiness = MagicMock()
    readiness.evaluate.return_value = MagicMock(ready=True, checks=[])
    risk = RiskManager(state=state, locks=locks, scheduler=scheduler, readiness_gate=readiness)
    orders = AsyncMock()
    orders.place_buy_order.return_value = {"success": True, "order_id": REAL_ORDER_ID}
    orders.confirm_order_execution.return_value = confirm_ok(100.0, 65)
    tracker = ManualValidationTracker()
    svc = ProductionValidationService(state, readiness, MagicMock(), MagicMock(), MagicMock(), scheduler, tracker)
    return ExecutionController(
        state, risk, locks, scheduler, readiness, orders, AsyncMock(),
        manual_tracker=tracker, validation_service=svc,
    )


def _signal() -> ExecutionSignal:
    return ExecutionSignal(
        engine="wick", action="BUY_CE", symbol="ATM_CE",
        tradingsymbol="NIFTY07JUL2624350CE", token="44649", exchange="NFO",
        premium=100.0, option_side="CE", strike=24350,
    )


@pytest.mark.asyncio
async def test_monitor_signals_do_not_consume_duplicate_lock():
    ctrl = _ctrl()
    ctrl.set_engine_mode("wick", EngineOperatingMode.MONITOR)
    for _ in range(5):
        result = await ctrl.process_signal(_signal())
        assert "MONITOR" in result.message
    ctrl.set_engine_mode("wick", EngineOperatingMode.AUTO)
    result = await ctrl.process_signal(_signal())
    assert result.state == ExecutionState.POSITION_ACTIVE


@pytest.mark.asyncio
async def test_rejected_auto_order_releases_duplicate_for_retry():
    ctrl = _ctrl()
    ctrl.set_engine_mode("wick", EngineOperatingMode.AUTO)
    ctrl._orders.place_buy_order.return_value = {"success": False, "message": "Rejected"}
    first = await ctrl.process_signal(_signal())
    assert first.state == ExecutionState.ORDER_REJECTED
    ctrl._orders.place_buy_order.return_value = {"success": True, "order_id": REAL_ORDER_ID_2}
    ctrl._orders.confirm_order_execution.return_value = confirm_ok(100.0, 65)
    second = await ctrl.process_signal(_signal())
    assert second.state == ExecutionState.POSITION_ACTIVE
    assert ctrl._orders.place_buy_order.await_count == 2
