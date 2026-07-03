"""Production hardening tests."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import REAL_ORDER_ID, confirm_ok

from app.broker.order_manager import OrderManager
from app.broker.websocket_manager import WebSocketManager
from app.core.sanitize import sanitize_broker_response
from app.core.state import AppState, MAX_TRADE_HISTORY
from app.execution.execution_controller import ExecutionController
from app.execution.execution_models import ExecutionResult
from app.models.enums import ExecutionState
from app.storage.position_store import PositionStore


def test_sanitize_broker_response_strips_raw_payload():
    raw = {
        "success": True,
        "order_id": "123",
        "response": {"status": True, "message": "ok", "data": {"jwtToken": "secret"}},
        "status": {"status": "complete", "orderid": "123", "averageprice": "100.5"},
    }
    safe = sanitize_broker_response(raw)
    assert "jwtToken" not in str(safe)
    assert safe["order_id"] == "123"
    assert safe["status"]["averageprice"] == "100.5"


@pytest.mark.asyncio
async def test_reconcile_order_fill_after_timeout():
    orders = OrderManager(MagicMock(), MagicMock())
    orders.get_order_status = AsyncMock(return_value={
        "status": "complete", "orderid": REAL_ORDER_ID, "averageprice": "105", "filledshares": "65",
    })
    orders.get_trade_book = AsyncMock(return_value=[{
        "orderid": REAL_ORDER_ID, "transactiontype": "BUY", "fillprice": "105", "fillsize": "65",
    }])
    result = await orders.reconcile_order_fill(REAL_ORDER_ID, expected_qty=65)
    assert result["success"] is True
    assert result["reconciled"] is True
    assert result["executed_price"] == 105.0


@pytest.mark.asyncio
async def test_buy_unknown_state_recovered_via_reconcile():
    from app.risk.locks import TradingLocks
    from app.risk.risk_manager import RiskManager
    from app.scheduler.session_scheduler import SessionScheduler
    from app.execution.execution_models import ExecutionSignal

    state = AppState()
    state.set_available_margin(100000)
    sched = SessionScheduler()
    sched._new_entries_allowed = True
    readiness = MagicMock()
    readiness.evaluate.return_value = MagicMock(ready=True)
    orders = AsyncMock()
    orders.place_buy_order.return_value = {"success": True, "order_id": REAL_ORDER_ID}
    orders.confirm_order_execution.return_value = {"success": False, "message": "timeout"}
    orders.reconcile_order_fill.return_value = {
        "success": True,
        "executed_price": 55.0,
        "filled_qty": 65,
        "reconciled": True,
        "message": "Reconciled fill after timeout",
    }
    ctrl = ExecutionController(
        state,
        RiskManager(state, TradingLocks(), sched, readiness),
        TradingLocks(),
        sched,
        readiness,
        orders,
        AsyncMock(),
    )
    ctrl.set_engine_mode("normal", __import__("app.models.enums", fromlist=["EngineOperatingMode"]).EngineOperatingMode.AUTO)
    with (
        patch("app.execution.execution_controller.trading_now", return_value=datetime(2026, 7, 1, 10, 0, 0)),
        patch("app.risk.risk_manager.trading_now", return_value=datetime(2026, 7, 1, 10, 0, 0)),
    ):
        result = await ctrl.process_signal(ExecutionSignal(
            engine="normal", action="BUY_CE", symbol="ATM_CE",
            tradingsymbol="NIFTY24900CE", token="1", exchange="NFO",
            option_side="CE", premium=50.0, strike=24900,
        ))
    assert result.state == ExecutionState.POSITION_ACTIVE
    assert "normal" in state.live_positions


@pytest.mark.asyncio
async def test_exit_retains_position_on_unknown_confirm():
    from app.risk.locks import TradingLocks
    from app.risk.risk_manager import RiskManager
    from app.scheduler.session_scheduler import SessionScheduler
    from app.models.enums import ExitReason

    state = AppState()
    state.set_live_position("normal", {
        "tradingsymbol": "X", "token": "1", "quantity": 65,
        "entry_price": 50.0, "option_side": "CE",
    })
    sched = SessionScheduler()
    readiness = MagicMock()
    orders = AsyncMock()
    orders.place_sell_order.return_value = {"success": True, "order_id": "E1"}
    orders.confirm_order_execution.return_value = {"success": False, "message": "timeout"}
    orders.reconcile_order_fill.return_value = {"success": False, "reconciled": False, "message": "pending"}
    ctrl = ExecutionController(
        state,
        RiskManager(state, TradingLocks(), sched, readiness),
        TradingLocks(),
        sched,
        readiness,
        orders,
        AsyncMock(),
    )
    result = await ctrl.exit_engine("normal", ExitReason.MANUAL)
    assert result.state == ExecutionState.UNKNOWN_ORDER_STATE
    assert "normal" in state.live_positions


def test_trade_history_capped():
    state = AppState()
    pos = {"entry_order_id": "1", "quantity": 65, "entry_price": 10.0}
    for i in range(MAX_TRADE_HISTORY + 10):
        state.record_trade("normal", pos, 11.0, f"E{i}", 65.0, "TARGET")
    assert len(state.trade_history) == MAX_TRADE_HISTORY


def test_position_store_atomic_write(tmp_path):
    store = PositionStore(path=tmp_path / "live_positions.json")
    store.save({"normal": {"engine": "normal", "token": "1"}})
    assert store.load()["normal"]["token"] == "1"


def test_execution_result_to_dict_sanitizes_broker_response():
    result = ExecutionResult(
        "r1", "normal", ExecutionState.ORDER_CONFIRMED, "ok",
        broker_response={"success": True, "response": {"data": {"jwtToken": "x"}}},
    )
    dumped = result.to_dict()
    assert "jwtToken" not in str(dumped["broker_response"])


def test_websocket_stops_old_connection_before_reconnect():
    ws = WebSocketManager()
    old = MagicMock()
    ws._ws = old
    ws._reconnect_creds = {
        "jwt_token": "j", "feed_token": "f", "client_code": "c",
        "api_key": "k", "subscriptions": {},
    }
    with patch.object(ws, "_build_token_list", return_value=[]):
        with patch("SmartApi.smartWebSocketV2.SmartWebSocketV2") as mock_sws:
            mock_sws.return_value = MagicMock()
            with patch("threading.Thread") as mock_thread:
                mock_thread.return_value.start = MagicMock()
                ws._start_ws_thread("j", "f", "c", "k", {})
    old.close_connection.assert_called_once()
