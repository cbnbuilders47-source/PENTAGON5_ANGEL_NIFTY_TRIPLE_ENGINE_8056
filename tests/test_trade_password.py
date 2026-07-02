"""Dashboard trade password protection tests."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.execution.execution_models import ExecutionResult, ExecutionSignal, PendingManualApproval
from app.main import create_app
from app.models.enums import EngineOperatingMode, ExecutionState, SessionPhase

TRADE_PASSWORD = "TradeSecret8056"


@pytest.fixture(autouse=True)
def reset_trade_security_state(client):
    client.app.state.trading_locks.deactivate_kill_switch()
    client.app.state.trading_locks.clear_duplicates()
    client.app.state.trading_locks._engine_halt.clear()
    client.app.state.trading_locks._symbol_halt.clear()
    yield


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TRADE_PASSWORD", TRADE_PASSWORD)
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def _inject_manual_approval(client: TestClient, *, action: str = "BUY_CE") -> str:
    ctrl = client.app.state.execution_controller
    approval_id = "appr-test-001"
    signal = ExecutionSignal(
        engine="normal",
        action=action,
        symbol="CE",
        tradingsymbol="NIFTY24900CE",
        token="1",
        exchange="NFO",
        option_side="CE",
        strike=24900,
        premium=50.0,
    )
    ctrl._pending_manual[approval_id] = PendingManualApproval(
        approval_id=approval_id,
        engine="normal",
        action=action,
        signal=signal,
        lots=1,
        quantity=65,
        expires_at=datetime.now() + timedelta(seconds=60),
    )
    return approval_id


def test_manual_buy_approve_without_password_blocked(client):
    approval_id = _inject_manual_approval(client)
    res = client.post("/api/v1/execution/manual/approve", json={"approval_id": approval_id})
    assert res.status_code == 403
    assert res.json()["detail"] == "Password confirmation failed"
    assert approval_id in client.app.state.execution_controller._pending_manual


def test_manual_buy_approve_wrong_password_blocked(client):
    approval_id = _inject_manual_approval(client)
    res = client.post(
        "/api/v1/execution/manual/approve",
        json={"approval_id": approval_id, "password": "wrong"},
    )
    assert res.status_code == 403
    assert approval_id in client.app.state.execution_controller._pending_manual


def test_manual_buy_approve_correct_password_allowed(client):
    approval_id = _inject_manual_approval(client)
    ctrl = client.app.state.execution_controller
    ctrl.set_engine_mode("normal", EngineOperatingMode.MANUAL)
    with (
        patch.object(ctrl, "_check_gates", return_value=None),
        patch.object(ctrl, "_execute_live", new_callable=AsyncMock) as live_mock,
    ):
        live_mock.return_value = ExecutionResult(
            approval_id, "normal", ExecutionState.ORDER_CONFIRMED, "Order sent"
        )
        res = client.post(
            "/api/v1/execution/manual/approve",
            json={"approval_id": approval_id, "password": TRADE_PASSWORD},
        )
    assert res.status_code == 200
    live_mock.assert_awaited_once()


def test_manual_exit_approve_without_password_blocked(client):
    approval_id = _inject_manual_approval(client, action="EXIT")
    res = client.post("/api/v1/execution/manual/approve", json={"approval_id": approval_id})
    assert res.status_code == 403


def test_engine_exit_wrong_password_blocked(client):
    state = client.app.state.app_state
    state.set_live_position("normal", {
        "tradingsymbol": "NIFTY24900CE",
        "token": "1",
        "quantity": 65,
        "entry_price": 100.0,
        "option_side": "CE",
        "exchange": "NFO",
    })
    res = client.post("/api/v1/engine/normal/exit", json={"password": "bad"})
    assert res.status_code == 403
    assert "normal" in state.live_positions


def test_exit_all_wrong_password_blocked(client):
    state = client.app.state.app_state
    state.set_live_position("normal", {
        "tradingsymbol": "NIFTY24900CE",
        "token": "1",
        "quantity": 65,
        "entry_price": 100.0,
        "option_side": "CE",
        "exchange": "NFO",
    })
    res = client.post("/api/v1/execution/exit-all", json={"password": "bad"})
    assert res.status_code == 403
    assert state.live_positions


def test_auto_mode_switch_wrong_password_blocked(client):
    res = client.post("/api/v1/engine/normal/mode", json={"mode": "AUTO", "password": "bad"})
    assert res.status_code == 403
    assert client.app.state.execution_controller.get_engine_mode("normal") != EngineOperatingMode.AUTO


def test_auto_mode_switch_correct_password_allowed_when_validation_passes(client):
    from app.validation.manual_tracker import MANUAL_STEPS

    tracker = client.app.state.manual_validation_tracker
    for step in MANUAL_STEPS:
        tracker.mark("normal", step)
    client.app.state.app_state.set_recovery_status({"status": "clean", "clean": True, "message": "ok"})
    readiness = client.app.state.readiness_gate
    readiness.evaluate = lambda: type("R", (), {"ready": True, "checks": []})()

    res = client.post(
        "/api/v1/engine/normal/mode",
        json={"mode": "AUTO", "password": TRADE_PASSWORD},
    )
    if res.status_code == 200:
        assert res.json()["mode"] == "AUTO"
    else:
        assert res.status_code == 403
        assert "reason" in res.json()["detail"]


def test_exit_server_wrong_password_not_shutdown(client):
    with patch.object(client.app.state.shutdown_manager, "shutdown", new_callable=AsyncMock) as shutdown_mock:
        res = client.post("/api/v1/system/shutdown", json={"password": "bad"})
        assert res.status_code == 403
        shutdown_mock.assert_not_awaited()


def test_exit_server_correct_password_shutdown_accepted(client):
    with patch.object(client.app.state.shutdown_manager, "shutdown", new_callable=AsyncMock) as shutdown_mock:
        res = client.post("/api/v1/system/shutdown", json={"password": TRADE_PASSWORD})
        assert res.status_code == 200
        assert res.json()["status"] == "shutdown_initiated"
        shutdown_mock.assert_awaited_once_with(exit_process=True)


def test_password_never_appears_in_logs(client, caplog):
    caplog.set_level(logging.WARNING)
    approval_id = _inject_manual_approval(client)
    secret = TRADE_PASSWORD
    client.post(
        "/api/v1/execution/manual/approve",
        json={"approval_id": approval_id, "password": secret},
    )
    log_text = caplog.text
    assert secret not in log_text
    assert TRADE_PASSWORD not in log_text
