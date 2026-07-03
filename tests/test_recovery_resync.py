"""Recovery resync and production broker wiring tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.broker.order_manager import OrderManager
from app.core.state import AppState
from app.execution.recovery import ExecutionRecovery
from app.storage.position_store import PositionStore


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
async def test_recovery_infers_engine_from_execution_audit(tmp_path):
    state = AppState()
    state.set_broker_connected(True)
    audit_file = tmp_path / "execution_audit.log"
    audit_file.write_text(
        "2026-07-03 12:53:08 | exec_pipeline | "
        "{'stage': '7_place_buy_order_call', 'engine': 'wick', 'token': '44649', "
        "'tradingsymbol': 'NIFTY07JUL2624350CE', 'qty': 65}\n",
        encoding="utf-8",
    )
    orders = AsyncMock()
    orders.get_order_book.return_value = []
    orders.get_trade_book.return_value = []
    positions = AsyncMock()
    positions.sync_positions_with_status.return_value = (
        [{"symboltoken": "44649", "tradingsymbol": "NIFTY07JUL2624350CE", "netqty": "65", "ltp": "100"}],
        True,
    )
    store = MagicMock()
    store.load.return_value = {}
    recovery = ExecutionRecovery(state, orders, positions, position_store=store)
    with patch("app.execution.recovery.get_settings") as mock_settings:
        mock_settings.return_value.logs_dir = tmp_path
        summary = await recovery.resync()
    assert summary["status"] == "clean"
    assert summary["positions_recovered"] == 1
    assert "wick" in state.live_positions
    assert state.live_positions["wick"]["token"] == "44649"


def test_production_order_manager_requires_live_angel_session():
    angel = MagicMock()
    angel.smart_api = None
    om = OrderManager(angel, MagicMock())
    with pytest.raises(RuntimeError, match="Angel session not connected"):
        om._api()
