"""Broker-truth and dashboard sync regression tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.broker.broker_verify import is_valid_angel_order_id, parse_nifty_option_symbol
from app.broker.order_manager import OrderManager
from app.core.state import AppState
from app.dashboard.sync import assess_broker_desync, build_latest_order_view, enrich_position
from app.execution.execution_controller import ExecutionController
from app.execution.execution_models import ExecutionSignal
from app.execution.recovery import ExecutionRecovery
from app.models.enums import EngineOperatingMode
from app.risk.locks import TradingLocks
from app.risk.risk_manager import RiskManager
from app.scheduler.session_scheduler import SessionScheduler
from app.storage.position_store import PositionStore


REAL_ORDER_ID = "240703000123456"


def test_reject_test_order_ids():
    assert is_valid_angel_order_id("O1") is False
    assert is_valid_angel_order_id("E1") is False
    assert is_valid_angel_order_id("1") is False
    assert is_valid_angel_order_id(REAL_ORDER_ID) is True


def test_parse_nifty_option_symbol():
    parsed = parse_nifty_option_symbol("NIFTY07JUL2624350CE")
    assert parsed["strike"] == 24350
    assert parsed["option_side"] == "CE"


@pytest.mark.asyncio
async def test_place_order_fake_o1_rejected_no_position():
    state = AppState()
    state.set_available_margin(100000)
    sched = SessionScheduler()
    sched._new_entries_allowed = True
    readiness = MagicMock()
    readiness.evaluate.return_value = MagicMock(ready=True)
    orders = AsyncMock()
    orders.place_buy_order.return_value = {"success": True, "order_id": "O1"}
    ctrl = ExecutionController(
        state,
        RiskManager(state, TradingLocks(), sched, readiness),
        TradingLocks(),
        sched,
        readiness,
        orders,
        AsyncMock(),
    )
    state.set_engine_mode("wick", EngineOperatingMode.AUTO)
    state.supervised_auto_enabled = True
    state.set_recovery_status({"status": "clean", "clean": True})
    signal = ExecutionSignal(
        engine="wick", action="BUY_CE", symbol="ATM_CE",
        tradingsymbol="NIFTY07JUL2624350CE", token="44649", exchange="NFO",
        strike=24350, option_side="CE", premium=90.0,
    )
    with patch("app.execution.execution_controller.trading_now", return_value=__import__("datetime").datetime(2026, 7, 3, 10, 0)):
        with patch("app.risk.risk_manager.trading_now", return_value=__import__("datetime").datetime(2026, 7, 3, 10, 0)):
            result = await ctrl.process_signal(signal)
    assert result.state.value == "ORDER_REJECTED"
    assert "wick" not in state.live_positions


@pytest.mark.asyncio
async def test_confirm_without_order_book_does_not_create_position():
    state = AppState()
    state.set_available_margin(100000)
    sched = SessionScheduler()
    sched._new_entries_allowed = True
    readiness = MagicMock()
    readiness.evaluate.return_value = MagicMock(ready=True)
    orders = AsyncMock()
    orders.place_buy_order.return_value = {"success": True, "order_id": REAL_ORDER_ID}
    orders.confirm_order_execution.return_value = {"success": False, "message": "Order not found in Angel order book"}
    orders.reconcile_order_fill.return_value = {"success": False, "message": "Order not found in Angel order book", "reconciled": False}
    ctrl = ExecutionController(
        state,
        RiskManager(state, TradingLocks(), sched, readiness),
        TradingLocks(),
        sched,
        readiness,
        orders,
        AsyncMock(),
    )
    state.set_engine_mode("wick", EngineOperatingMode.AUTO)
    state.supervised_auto_enabled = True
    state.set_recovery_status({"status": "clean", "clean": True})
    signal = ExecutionSignal(
        engine="wick", action="BUY_CE", symbol="ATM_CE",
        tradingsymbol="NIFTY07JUL2624350CE", token="44649", exchange="NFO",
        strike=24350, option_side="CE", premium=90.0,
    )
    with patch("app.execution.execution_controller.trading_now", return_value=__import__("datetime").datetime(2026, 7, 3, 10, 0)):
        with patch("app.risk.risk_manager.trading_now", return_value=__import__("datetime").datetime(2026, 7, 3, 10, 0)):
            result = await ctrl.process_signal(signal)
    assert result.state.value in ("ORDER_REJECTED", "UNKNOWN_ORDER_STATE")
    assert "wick" not in state.live_positions


@pytest.mark.asyncio
async def test_recovery_clears_app_position_when_broker_flat(tmp_path):
    state = AppState()
    state.set_broker_connected(True)
    state.set_live_position("wick", {
        "engine": "wick",
        "token": "44649",
        "tradingsymbol": "NIFTY07JUL2624350CE",
        "quantity": 65,
        "entry_price": 85.9,
        "recovered": True,
    })
    orders = AsyncMock()
    orders.get_order_book.return_value = []
    orders.get_trade_book.return_value = []
    positions = AsyncMock()
    positions.sync_positions_with_status.return_value = ([], True)
    store = PositionStore(path=tmp_path / "live_positions.json")
    recovery = ExecutionRecovery(state, orders, positions, position_store=store)
    summary = await recovery.resync()
    assert "wick" not in state.live_positions
    assert summary.get("cleared_engines") == ["wick"]
    assert summary["status"] == "clean"


@pytest.mark.asyncio
async def test_recovery_requires_confirmed_buy_order():
    state = AppState()
    state.set_broker_connected(True)
    orders = AsyncMock()
    orders.get_order_book.return_value = []
    orders.get_trade_book.return_value = []
    positions = AsyncMock()
    positions.sync_positions_with_status.return_value = (
        [{"symboltoken": "44649", "tradingsymbol": "NIFTY07JUL2624350CE", "netqty": "65", "ltp": "90"}],
        True,
    )
    store = MagicMock()
    store.load.return_value = {}
    recovery = ExecutionRecovery(state, orders, positions, position_store=store)
    summary = await recovery.resync()
    assert "wick" not in state.live_positions
    assert summary["status"] == "dirty"
    assert summary["unknown_positions"] == 1


def test_dashboard_desync_flag():
    state = AppState()
    state.set_live_position("wick", {
        "token": "44649",
        "tradingsymbol": "NIFTY07JUL2624350CE",
        "quantity": 65,
        "entry_price": 85.9,
    })
    desync = assess_broker_desync(state.live_positions, [])
    assert desync["critical"] is True
    latest = build_latest_order_view(state, MagicMock(status=lambda: {"recent": []}), 24350)
    assert latest["state"] == "BROKER_DESYNC"


def test_enrich_position_strike_and_side():
    pos = enrich_position({"tradingsymbol": "NIFTY07JUL2624350CE", "quantity": 65, "entry_price": 85, "current_ltp": 90})
    assert pos["strike"] == 24350
    assert pos["action_label"] == "BUY CE"


def test_production_order_manager_requires_live_angel_session():
    om = OrderManager(MagicMock(smart_api=None), MagicMock())
    with pytest.raises(RuntimeError, match="Angel session not connected"):
        om._api()
