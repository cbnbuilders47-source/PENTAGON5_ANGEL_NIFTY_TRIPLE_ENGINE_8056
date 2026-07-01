"""Exit monitor and position LTP update tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.state import AppState
from app.execution.execution_controller import ExecutionController
from app.models.enums import ExitReason
from app.risk.exit_monitor import ExitMonitor
from app.risk.locks import TradingLocks
from app.risk.risk_manager import RiskManager
from app.scheduler.session_scheduler import SessionScheduler


def _make_exit_monitor(state: AppState | None = None):
    state = state or AppState()
    controller = AsyncMock(spec=ExecutionController)
    controller.exit_engine = AsyncMock()
    controller.exit_all = AsyncMock()
    scheduler = SessionScheduler()
    scheduler._force_exit_active = False
    return ExitMonitor(state, controller, scheduler), controller


def test_position_ltp_updates_from_atm_tick():
    state = AppState()
    state.set_live_position("normal", {
        "option_side": "CE",
        "entry_price": 100.0,
        "current_ltp": 100.0,
        "target": 110.0,
        "stop_loss": 90.0,
        "tradingsymbol": "NIFTY24900CE",
        "token": "1",
        "quantity": 50,
    })
    state.update_position_ltp_from_tick("ATM_CE", 112.0)
    assert state.live_positions["normal"]["current_ltp"] == 112.0
    state.update_position_ltp_from_tick("ATM_PE", 80.0)
    assert state.live_positions["normal"]["current_ltp"] == 112.0


@pytest.mark.asyncio
async def test_exit_monitor_triggers_target_on_fresh_ltp():
    monitor, controller = _make_exit_monitor()
    state = monitor._state
    state.set_live_position("wick", {
        "option_side": "PE",
        "entry_price": 100.0,
        "current_ltp": 115.0,
        "target": 110.0,
        "stop_loss": 90.0,
        "tradingsymbol": "NIFTY24900PE",
        "token": "2",
        "quantity": 50,
    })
    await monitor.evaluate()
    controller.exit_engine.assert_awaited_once_with("wick", ExitReason.TARGET)


@pytest.mark.asyncio
async def test_exit_monitor_force_exit():
    monitor, controller = _make_exit_monitor()
    monitor._state.force_exit_active = True
    await monitor.evaluate()
    controller.exit_all.assert_awaited_once_with(ExitReason.FORCE_EXIT)
