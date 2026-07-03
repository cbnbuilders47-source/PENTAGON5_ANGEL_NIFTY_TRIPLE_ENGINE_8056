"""Special No-Entry Window (14:57–15:01 IST) tests."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import REAL_ORDER_ID, confirm_ok

from app.core.constants import ENGINE_NORMAL, ENGINE_ULTRA, ENGINE_WICK
from app.core.state import AppState
from app.execution.execution_controller import ExecutionController
from app.execution.execution_models import ExecutionSignal
from app.intelligence.time_rules import (
    engine_buy_blocked_special_window,
    engine_new_entries_allowed,
    special_no_entry_block_message,
)
from app.models.enums import EngineOperatingMode, ExecutionState, ExitReason
from app.risk.exit_monitor import ExitMonitor
from app.risk.locks import TradingLocks
from app.risk.risk_manager import RiskManager
from app.scheduler.session_scheduler import SessionScheduler


def _dt(h: int, m: int, s: int = 0) -> datetime:
    return datetime(2026, 7, 1, h, m, s)


@pytest.mark.parametrize(
    "engine,at,allowed",
    [
        (ENGINE_NORMAL, _dt(14, 56, 59), True),
        (ENGINE_ULTRA, _dt(14, 56, 59), True),
        (ENGINE_WICK, _dt(14, 56, 59), True),
        (ENGINE_NORMAL, _dt(14, 57, 0), False),
        (ENGINE_ULTRA, _dt(14, 57, 0), False),
        (ENGINE_WICK, _dt(14, 57, 0), True),
        (ENGINE_NORMAL, _dt(14, 59, 0), False),
        (ENGINE_ULTRA, _dt(14, 59, 0), False),
        (ENGINE_WICK, _dt(14, 59, 0), True),
        (ENGINE_NORMAL, _dt(15, 1, 0), True),
        (ENGINE_ULTRA, _dt(15, 1, 0), True),
        (ENGINE_WICK, _dt(15, 1, 0), True),
    ],
)
def test_engine_new_entries_allowed_special_window(engine, at, allowed):
    assert engine_new_entries_allowed(engine, at) is allowed


def test_special_no_entry_block_messages():
    assert special_no_entry_block_message(ENGINE_NORMAL, _dt(14, 58)) == (
        "Normal Engine blocked during Special No-Entry Window (14:57–15:01)"
    )
    assert special_no_entry_block_message(ENGINE_ULTRA, _dt(14, 58)) == (
        "Ultra Engine blocked during Special No-Entry Window (14:57–15:01)"
    )
    assert special_no_entry_block_message(ENGINE_WICK, _dt(14, 58)) is None


def test_wick_allowed_between_stop_new_entries_and_wick_end():
    assert engine_new_entries_allowed(ENGINE_WICK, _dt(15, 12, 0)) is True
    assert engine_new_entries_allowed(ENGINE_NORMAL, _dt(15, 12, 0)) is False


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
    orders.place_buy_order.return_value = {"success": True, "order_id": REAL_ORDER_ID}
    orders.confirm_order_execution.return_value = confirm_ok(100.0, 65)
    positions = AsyncMock()
    risk = RiskManager(state=state, locks=locks, scheduler=scheduler, readiness_gate=readiness)
    return ExecutionController(state, risk, locks, scheduler, readiness, orders, positions)


def _signal(engine: str = "normal") -> ExecutionSignal:
    return ExecutionSignal(
        engine=engine,
        action="BUY_CE",
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
@patch("app.execution.execution_controller.trading_now")
async def test_execution_blocks_normal_during_special_window(mock_now):
    mock_now.return_value = _dt(14, 57, 30)
    ctrl = _make_controller()
    ctrl.set_engine_mode("normal", EngineOperatingMode.AUTO)
    result = await ctrl.process_signal(_signal("normal"))
    assert result.state == ExecutionState.BLOCKED_BY_TIME
    assert "Special No-Entry Window" in result.message


@pytest.mark.asyncio
@patch("app.risk.risk_manager.trading_now")
@patch("app.execution.execution_controller.trading_now")
async def test_execution_allows_wick_during_special_window(mock_ctrl_now, mock_risk_now):
    mock_ctrl_now.return_value = _dt(14, 59, 0)
    mock_risk_now.return_value = _dt(14, 59, 0)
    ctrl = _make_controller()
    ctrl.set_engine_mode("wick", EngineOperatingMode.AUTO)
    result = await ctrl.process_signal(_signal("wick"))
    assert result.state in (ExecutionState.ORDER_CONFIRMED, ExecutionState.POSITION_ACTIVE)


@pytest.mark.asyncio
@patch("app.risk.risk_manager.trading_now")
@patch("app.execution.execution_controller.trading_now")
async def test_execution_allows_normal_after_special_window(mock_ctrl_now, mock_risk_now):
    mock_ctrl_now.return_value = _dt(15, 1, 0)
    mock_risk_now.return_value = _dt(15, 1, 0)
    ctrl = _make_controller()
    ctrl.set_engine_mode("normal", EngineOperatingMode.AUTO)
    result = await ctrl.process_signal(_signal("normal"))
    assert result.state in (ExecutionState.ORDER_CONFIRMED, ExecutionState.POSITION_ACTIVE)


@patch("app.risk.risk_manager.trading_now")
def test_risk_manager_blocks_normal_during_special_window(mock_now):
    mock_now.return_value = _dt(14, 58, 0)
    state = AppState()
    state.set_available_margin(100000)
    sched = SessionScheduler()
    sched._new_entries_allowed = True
    risk = RiskManager(state, TradingLocks(), sched)
    allowed, reason = risk.can_open_position("normal", "NIFTY24900CE", "hash1")
    assert allowed is False
    assert "Normal Engine blocked during Special No-Entry Window" in reason


@patch("app.risk.risk_manager.trading_now")
def test_risk_manager_allows_wick_during_special_window(mock_now):
    mock_now.return_value = _dt(14, 58, 0)
    state = AppState()
    state.set_available_margin(100000)
    risk = RiskManager(state, TradingLocks(), SessionScheduler(), readiness_gate=None)
    allowed, reason = risk.can_open_position("wick", "NIFTY24900PE", "hash2")
    assert allowed is True


@pytest.mark.asyncio
async def test_exit_monitor_continues_during_special_window():
    state = AppState()
    state.set_live_position("normal", {
        "option_side": "CE",
        "entry_price": 100.0,
        "current_ltp": 115.0,
        "target": 110.0,
        "stop_loss": 90.0,
        "tradingsymbol": "NIFTY24900CE",
        "token": "1",
        "quantity": 50,
    })
    controller = AsyncMock(spec=ExecutionController)
    controller.exit_engine = AsyncMock()
    scheduler = SessionScheduler()
    scheduler._force_exit_active = False
    monitor = ExitMonitor(state, controller, scheduler)

    with patch("app.intelligence.time_rules.is_special_no_entry_window", return_value=True):
        await monitor.evaluate()

    controller.exit_engine.assert_awaited_once_with("normal", ExitReason.TARGET)


@pytest.mark.asyncio
@patch("app.risk.risk_manager.trading_now")
@patch("app.execution.execution_controller.trading_now")
async def test_force_exit_at_1514_overrides_special_window(mock_ctrl_now, mock_risk_now):
    mock_ctrl_now.return_value = _dt(15, 14, 30)
    mock_risk_now.return_value = _dt(15, 14, 30)
    ctrl = _make_controller()
    ctrl.set_engine_mode("wick", EngineOperatingMode.AUTO)
    ctrl._state.force_exit_active = True
    result = await ctrl.process_signal(_signal("wick"))
    assert result.state == ExecutionState.BLOCKED_BY_TIME
    assert "Force-exit" in result.message


def test_scheduler_fires_special_window_events():
    sched = SessionScheduler()
    sched.tick(_dt(14, 57, 0))
    labels = [e["label"] for e in sched.tick(_dt(14, 57, 1)).events_today if e["fired"]]
    assert "special_no_entry_start" in labels
