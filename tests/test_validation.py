"""Production validation and resilience tests."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.state import AppState
from app.execution.execution_controller import ExecutionController
from app.execution.execution_models import ExecutionSignal
from app.execution.recovery import ExecutionRecovery
from app.models.enums import EngineOperatingMode, EngineStatus, ExecutionState, SessionPhase
from app.risk.locks import TradingLocks
from app.risk.risk_manager import RiskManager
from app.scheduler.session_scheduler import SessionScheduler
from app.validation.manual_tracker import MANUAL_STEPS, ManualValidationTracker
from app.validation.validation_service import ProductionValidationService
from app.broker.websocket_manager import WebSocketManager, _BASE_BACKOFF_SEC, _MAX_BACKOFF_SEC
from app.main import create_app

TRADING_HOUR = datetime(2026, 7, 1, 10, 0, 0)


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def _validation_stack(state: AppState | None = None):
    state = state or AppState()
    state.set_available_margin(100000)
    state.apply_scheduler_status(MagicMock(
        current_phase=SessionPhase.TRADING,
        bias_locked=True,
        new_entries_allowed=True,
        force_exit_active=False,
    ))
    tracker = ManualValidationTracker()
    readiness = MagicMock()
    readiness.evaluate.return_value = MagicMock(
        ready=True,
        checks=[MagicMock(name="angel_connected", passed=True, message="ok")],
    )
    candles = MagicMock()
    candles.get_last_tick_at.return_value = datetime.now()
    atm = MagicMock(atm_strike=24900)
    instruments = MagicMock(selected_expiry="2026-07-03")
    scheduler = SessionScheduler()
    scheduler._new_entries_allowed = True
    svc = ProductionValidationService(state, readiness, candles, atm, instruments, scheduler, tracker)
    locks = TradingLocks()
    risk = RiskManager(state=state, locks=locks, scheduler=scheduler, readiness_gate=readiness)
    orders = AsyncMock()
    positions = AsyncMock()
    ctrl = ExecutionController(
        state, risk, locks, scheduler, readiness, orders, positions,
        manual_tracker=tracker, validation_service=svc,
    )
    return state, tracker, svc, ctrl


def test_validation_status_api(client):
    res = client.get("/api/v1/validation/status")
    assert res.status_code == 200
    data = res.json()
    assert "ready_for_manual_validation" in data
    assert "ready_for_auto_validation" in data
    assert "missing_checks" in data
    assert "validation_notes" in data
    assert data["ready_for_auto_validation"] is False


def test_manual_validation_api(client):
    res = client.get("/api/v1/validation/manual")
    assert res.status_code == 200
    data = res.json()
    assert "engines" in data
    assert data["normal_manual_cycle_passed"] is False


def test_manual_validation_reset(client):
    res = client.post("/api/v1/validation/manual/reset?engine=normal")
    assert res.status_code == 200
    assert res.json()["reset"] is True


def test_auto_blocked_before_manual_validation():
    _, _, svc, ctrl = _validation_stack()
    reason = ctrl.set_engine_mode("normal", EngineOperatingMode.AUTO)
    assert reason == "Manual validation not completed"
    assert ctrl.get_engine_mode("normal") == EngineOperatingMode.MONITOR


def test_auto_allowed_after_manual_validation_and_readiness():
    state, tracker, svc, ctrl = _validation_stack()
    state.set_recovery_status({"status": "clean", "clean": True, "message": "ok"})
    for step in MANUAL_STEPS:
        tracker.mark("normal", step)
    reason = ctrl.set_engine_mode("normal", EngineOperatingMode.AUTO)
    assert reason is None
    assert ctrl.get_engine_mode("normal") == EngineOperatingMode.AUTO


def test_auto_blocked_when_readiness_incomplete():
    state, tracker, svc, ctrl = _validation_stack()
    for step in MANUAL_STEPS:
        tracker.mark("normal", step)
    svc._readiness.evaluate.return_value = MagicMock(ready=False, checks=[])
    reason = ctrl.set_engine_mode("normal", EngineOperatingMode.AUTO)
    assert reason and reason.startswith("Broker readiness incomplete")


def test_auto_api_returns_403_when_blocked(client):
    res = client.post(
        "/api/v1/engine/normal/mode",
        json={"mode": "AUTO"},
    )
    assert res.status_code == 403
    assert "reason" in res.json()["detail"]


def test_manual_validation_lifecycle():
    with (
        patch("app.execution.execution_controller.trading_now") as ctrl_now,
        patch("app.risk.risk_manager.trading_now") as risk_now,
    ):
        ctrl_now.return_value = TRADING_HOUR
        risk_now.return_value = TRADING_HOUR
        _, tracker, _, ctrl = _validation_stack()
        ctrl.set_engine_mode("normal", EngineOperatingMode.MANUAL)

        async def run():
            result = await ctrl.process_signal(ExecutionSignal(
                engine="normal", action="BUY_CE", symbol="CE",
                tradingsymbol="NIFTY24900CE", token="1", exchange="NFO",
                option_side="CE", premium=50.0,
            ))
            assert "approval" in result.message.lower()
            assert tracker.engine_status("normal")["steps"]["buy_signal_generated"]
            assert tracker.engine_status("normal")["steps"]["manual_approval_shown"]

            approval_id = list(ctrl.pending_manual.keys())[0]
            ctrl._orders.place_buy_order.return_value = {"success": True, "order_id": "O1"}
            ctrl._orders.confirm_order_execution.return_value = {"success": True, "executed_price": 55.0}
            await ctrl.approve_manual(approval_id)
            assert tracker.engine_status("normal")["steps"]["user_approval_received"]
            assert tracker.engine_status("normal")["steps"]["position_active"]

            ctrl.on_position_ltp_updated("normal")
            assert tracker.engine_status("normal")["steps"]["ltp_updating"]

            ctrl._orders.place_sell_order.return_value = {"success": True, "order_id": "O2"}
            ctrl._orders.confirm_order_execution.return_value = {"success": True, "executed_price": 60.0}
            await ctrl.exit_engine("normal")
            assert tracker.is_passed("normal")

        import asyncio
        asyncio.run(run())


def test_websocket_reconnect_backoff():
    ws = WebSocketManager()
    ws._reconnect_creds = {"jwt_token": "j", "feed_token": "f", "client_code": "c", "api_key": "k", "subscriptions": {}}
    ws._reconnect_attempt = 0
    delay1 = min(_MAX_BACKOFF_SEC, _BASE_BACKOFF_SEC * (2 ** 0))
    delay2 = min(_MAX_BACKOFF_SEC, _BASE_BACKOFF_SEC * (2 ** 1))
    assert delay1 == 3
    assert delay2 == 6


@pytest.mark.asyncio
async def test_recovery_status_clean():
    state = AppState()
    orders = AsyncMock()
    orders.get_order_book.return_value = []
    orders.get_trade_book.return_value = []
    positions = AsyncMock()
    positions.sync_positions.return_value = [
        {"symboltoken": "12345", "tradingsymbol": "NIFTY24JUL25000CE", "netqty": "65", "exchange": "NFO"},
    ]
    store = MagicMock()
    store.load.return_value = {
        "normal": {
            "engine": "normal",
            "token": "12345",
            "tradingsymbol": "NIFTY24JUL25000CE",
            "entry_price": 100.0,
            "target": 108.0,
            "stop_loss": 96.0,
            "trailing_sl": 97.0,
            "option_side": "CE",
            "quantity": 65,
        }
    }
    recovery = ExecutionRecovery(state, orders, positions, position_store=store)
    summary = await recovery.recover()
    assert summary["status"] == "clean"
    assert summary["positions_recovered"] == 1
    assert "normal" in state.live_positions
    assert state.live_positions["normal"]["target"] == 108.0
    assert state.recovery_status["clean"] is True


@pytest.mark.asyncio
async def test_recovery_status_dirty_on_unknown():
    state = AppState()
    orders = AsyncMock()
    orders.get_order_book.return_value = []
    orders.get_trade_book.return_value = []
    positions = AsyncMock()
    positions.sync_positions.return_value = [
        {"symboltoken": "99999", "tradingsymbol": "UNKNOWN", "netqty": "65"},
    ]
    store = MagicMock()
    store.load.return_value = {}
    recovery = ExecutionRecovery(state, orders, positions, position_store=store)
    summary = await recovery.recover()
    assert summary["status"] == "dirty"
    assert summary["unknown_positions"] == 1


@pytest.mark.asyncio
async def test_engine_reset_after_exit():
    state, tracker, svc, ctrl = _validation_stack()
    state.set_live_position("normal", {
        "engine": "normal", "tradingsymbol": "X", "token": "1",
        "quantity": 65, "entry_price": 50.0, "option_side": "CE",
    })
    state.engines["normal"].open_positions = 1
    state.engines["normal"].status = EngineStatus.ACTIVE
    ctrl._orders.place_sell_order.return_value = {"success": True, "order_id": "E1"}
    ctrl._orders.confirm_order_execution.return_value = {"success": True, "executed_price": 55.0}
    await ctrl.exit_engine("normal")
    assert "normal" not in state.live_positions
    assert state.engines["normal"].open_positions == 0
    assert state.engines["normal"].status == EngineStatus.IDLE


def test_context_builder_uses_state_session_phase():
    from app.engines.context_builder import build_context
    from app.market.candle_builder import CandleBuilder
    from app.models.enums import MarketMode

    state = AppState()
    state.session_phase = SessionPhase.TRADING
    ctx = build_context(state, CandleBuilder(), MarketMode.SLOW_TREND)
    assert ctx.session_phase == SessionPhase.TRADING


def test_operator_includes_validation_fields(client):
    res = client.get("/api/v1/dashboard/operator")
    assert res.status_code == 200
    data = res.json()
    assert "validation_status" in data
    assert "manual_validation_status" in data
    assert "auto_allowed_by_engine" in data
    assert "recovery_status" in data
    assert "reconnect_status" in data
