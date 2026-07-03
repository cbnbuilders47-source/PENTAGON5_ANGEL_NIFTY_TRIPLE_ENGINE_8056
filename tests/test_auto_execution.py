"""AUTO execution path and tradingsymbol resolution tests."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import REAL_ORDER_ID, confirm_ok

from app.core.state import AppState
from app.execution.execution_controller import ExecutionController
from app.execution.signal_bridge import decision_to_signal
from app.intelligence.types import EngineDecisionSnapshot
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


def _stack(supervised_auto: bool = False):
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
    tracker = ManualValidationTracker()
    readiness = MagicMock()
    readiness.evaluate.return_value = MagicMock(ready=True, checks=[MagicMock(passed=True)])
    candles = MagicMock()
    candles.get_last_tick_at.return_value = datetime.now()
    candles.get_candles.return_value = [MagicMock(close=100.0)]
    atm = MagicMock(
        atm_strike=24350,
        ce_token="111",
        pe_token="222",
        ce_tradingsymbol="NIFTY03JUL2524350CE",
        pe_tradingsymbol="NIFTY03JUL2524350PE",
    )
    instruments = MagicMock(selected_expiry="03JUL2026")
    instruments.symbol_for_token.return_value = None
    scheduler = SessionScheduler()
    scheduler._new_entries_allowed = True
    svc = ProductionValidationService(state, readiness, candles, atm, instruments, scheduler, tracker)
    locks = TradingLocks()
    risk = RiskManager(state=state, locks=locks, scheduler=scheduler, readiness_gate=readiness)
    orders = AsyncMock()
    orders.place_buy_order.return_value = {"success": True, "order_id": REAL_ORDER_ID}
    orders.confirm_order_execution.return_value = confirm_ok(100.0, 65)
    ctrl = ExecutionController(
        state, risk, locks, scheduler, readiness, orders, AsyncMock(),
        manual_tracker=tracker, validation_service=svc,
    )
    return state, ctrl, orders, atm, instruments, candles


def test_signal_bridge_uses_instrument_tradingsymbol():
    _, _, _, atm, instruments, candles = _stack()
    snap = EngineDecisionSnapshot(
        engine="wick",
        phase="ENTRY_READY",
        decision="WOULD_BUY_CE",
        reasons=["test"],
        confidence=80.0,
    )
    signal = decision_to_signal("wick", snap, instruments, atm, candles)
    assert signal is not None
    assert signal.tradingsymbol == "NIFTY03JUL2524350CE"
    assert signal.token == "111"


def test_supervised_auto_allows_mode_without_manual_cycle():
    state, ctrl, _, _, _, _ = _stack(supervised_auto=True)
    reason = ctrl.set_engine_mode("wick", EngineOperatingMode.AUTO)
    assert reason is None
    assert ctrl.get_engine_mode("wick") == EngineOperatingMode.AUTO


def test_auto_blocked_without_supervised_or_manual():
    _, ctrl, _, _, _, _ = _stack(supervised_auto=False)
    reason = ctrl.set_engine_mode("wick", EngineOperatingMode.AUTO)
    assert reason == "Manual validation not completed"


@pytest.mark.asyncio
async def test_auto_signal_calls_place_buy_order():
    state, ctrl, orders, _, _, _ = _stack(supervised_auto=True)
    ctrl.set_engine_mode("wick", EngineOperatingMode.AUTO)
    from app.execution.execution_models import ExecutionSignal

    signal = ExecutionSignal(
        engine="wick",
        action="BUY_CE",
        symbol="ATM_CE",
        tradingsymbol="NIFTY03JUL2524350CE",
        token="111",
        exchange="NFO",
        strike=24350,
        option_side="CE",
        premium=100.0,
    )
    result = await ctrl.process_signal(signal)
    assert result.state == ExecutionState.POSITION_ACTIVE
    orders.place_buy_order.assert_awaited_once()
    call = orders.place_buy_order.await_args.kwargs
    assert call["tradingsymbol"] == "NIFTY03JUL2524350CE"
    assert call["symboltoken"] == "111"
    assert "wick" in state.live_positions


@pytest.mark.asyncio
async def test_auto_broker_rejection_recorded():
    state, ctrl, orders, _, _, _ = _stack(supervised_auto=True)
    orders.place_buy_order.return_value = {
        "success": False,
        "message": "Invalid Token",
        "reason": "Angel placeOrder status=False: Invalid Token",
    }
    ctrl.set_engine_mode("wick", EngineOperatingMode.AUTO)
    from app.execution.execution_models import ExecutionSignal

    signal = ExecutionSignal(
        engine="wick", action="BUY_CE", symbol="ATM_CE",
        tradingsymbol="NIFTY03JUL2524350CE", token="111", exchange="NFO",
        premium=100.0, option_side="CE", strike=24350,
    )
    result = await ctrl.process_signal(signal)
    assert result.state == ExecutionState.ORDER_REJECTED
    assert "Invalid Token" in result.message
    assert not state.live_positions
