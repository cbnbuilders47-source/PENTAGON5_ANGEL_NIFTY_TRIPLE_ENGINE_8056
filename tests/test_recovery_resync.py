"""Recovery resync and production broker wiring tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.state import AppState
from app.execution.recovery import ExecutionRecovery
from app.storage.position_store import PositionStore

REAL_ORDER_ID = "240703000123456"


@pytest.mark.asyncio
async def test_recovery_clears_stale_snapshot_when_broker_flat(tmp_path):
    state = AppState()
    state.set_broker_connected(True)
    orders = AsyncMock()
    orders.get_order_book.return_value = []
    orders.get_trade_book.return_value = []
    positions = AsyncMock()
    positions.sync_positions_with_status.return_value = ([], True)
    store = PositionStore(path=tmp_path / "live_positions.json")
    store.save({
        "wick": {
            "engine": "wick",
            "token": "1",
            "tradingsymbol": "NIFTY24900CE",
            "quantity": 65,
        }
    })
    recovery = ExecutionRecovery(state, orders, positions, position_store=store)
    summary = await recovery.resync()
    assert summary["status"] == "clean"
    assert summary["stale_snapshot_cleared"] is True
    assert store.load() == {}
    assert state.recovery_status["clean"] is True


@pytest.mark.asyncio
async def test_recovery_stays_dirty_when_broker_has_unmapped_position():
    state = AppState()
    state.set_broker_connected(True)
    orders = AsyncMock()
    orders.get_order_book.return_value = []
    orders.get_trade_book.return_value = []
    positions = AsyncMock()
    positions.sync_positions_with_status.return_value = (
        [{"symboltoken": "99999", "tradingsymbol": "UNKNOWN", "netqty": "65"}],
        True,
    )
    store = MagicMock()
    store.load.return_value = {}
    recovery = ExecutionRecovery(state, orders, positions, position_store=store)
    summary = await recovery.resync()
    assert summary["status"] == "dirty"
    assert summary["unknown_positions"] == 1
    assert summary["unknown_details"][0]["tradingsymbol"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_recovery_with_broker_and_order_book():
    state = AppState()
    state.set_broker_connected(True)
    orders = AsyncMock()
    orders.get_order_book.return_value = [{
        "orderid": REAL_ORDER_ID,
        "symboltoken": "44649",
        "tradingsymbol": "NIFTY07JUL2624350CE",
        "transactiontype": "BUY",
        "status": "complete",
        "averageprice": "100",
        "filledshares": "65",
    }]
    orders.get_trade_book.return_value = [{
        "orderid": REAL_ORDER_ID,
        "symboltoken": "44649",
        "tradingsymbol": "NIFTY07JUL2624350CE",
        "transactiontype": "BUY",
        "fillprice": "100",
        "fillsize": "65",
    }]
    positions = AsyncMock()
    positions.sync_positions_with_status.return_value = (
        [{"symboltoken": "44649", "tradingsymbol": "NIFTY07JUL2624350CE", "netqty": "65", "ltp": "100"}],
        True,
    )
    state.execution_results.append({
        "engine": "wick",
        "order_id": REAL_ORDER_ID,
        "state": "POSITION_ACTIVE",
    })
    store = MagicMock()
    store.load.return_value = {}
    recovery = ExecutionRecovery(state, orders, positions, position_store=store)
    summary = await recovery.resync()
    assert summary["status"] == "clean"
    assert summary["positions_recovered"] == 1
    assert "wick" in state.live_positions
    assert state.live_positions["wick"]["broker_verified"] is True
    assert state.live_positions["wick"]["strike"] == 24350
