"""Dashboard password protection — wakeup and shutdown only."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

DASHBOARD_PASSWORD = "TradeSecret8056"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TRADE_PASSWORD", DASHBOARD_PASSWORD)
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_wakeup_without_password_blocked(client):
    res = client.post("/api/v1/system/wakeup", json={})
    assert res.status_code == 403
    assert res.json()["detail"] == "Password verification failed"


def test_wakeup_wrong_password_blocked(client):
    res = client.post("/api/v1/system/wakeup", json={"password": "wrong"})
    assert res.status_code == 403
    assert res.json()["detail"] == "Password verification failed"


def test_wakeup_correct_password_allowed(client):
    res = client.post("/api/v1/system/wakeup", json={"password": DASHBOARD_PASSWORD})
    assert res.status_code == 200
    assert res.json()["status"] == "unlocked"


def test_manual_buy_approve_without_password_allowed(client):
    from datetime import datetime, timedelta

    from app.execution.execution_models import ExecutionSignal, PendingManualApproval

    ctrl = client.app.state.execution_controller
    approval_id = "appr-test-001"
    signal = ExecutionSignal(
        engine="normal",
        action="BUY_CE",
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
        action="BUY_CE",
        signal=signal,
        lots=1,
        quantity=65,
        expires_at=datetime.now() + timedelta(seconds=60),
    )
    from app.models.enums import EngineOperatingMode

    ctrl.set_engine_mode("normal", EngineOperatingMode.MANUAL)
    with (
        patch.object(ctrl, "_check_gates", return_value=None),
        patch.object(ctrl, "_execute_live", new_callable=AsyncMock) as live_mock,
    ):
        from app.execution.execution_models import ExecutionResult
        from app.models.enums import ExecutionState

        live_mock.return_value = ExecutionResult(
            approval_id, "normal", ExecutionState.ORDER_CONFIRMED, "Order sent"
        )
        res = client.post("/api/v1/execution/manual/approve", json={"approval_id": approval_id})
    assert res.status_code == 200
    live_mock.assert_awaited_once()


def test_engine_exit_without_password_allowed(client):
    state = client.app.state.app_state
    state.set_live_position("normal", {
        "tradingsymbol": "NIFTY24900CE",
        "token": "1",
        "quantity": 65,
        "entry_price": 100.0,
        "option_side": "CE",
        "exchange": "NFO",
    })
    with patch.object(
        client.app.state.execution_controller,
        "exit_engine",
        new_callable=AsyncMock,
    ) as exit_mock:
        from app.execution.execution_models import ExecutionResult
        from app.models.enums import ExecutionState

        exit_mock.return_value = ExecutionResult("x", "normal", ExecutionState.EXIT_CONFIRMED, "ok")
        res = client.post("/api/v1/engine/normal/exit")
    assert res.status_code == 200
    exit_mock.assert_awaited_once()


def test_exit_all_without_password_allowed(client):
    with patch.object(
        client.app.state.execution_controller,
        "exit_all",
        new_callable=AsyncMock,
        return_value=[],
    ) as exit_mock:
        res = client.post("/api/v1/execution/exit-all")
    assert res.status_code == 200
    exit_mock.assert_awaited_once()


def test_auto_mode_switch_without_password_blocked_by_validation(client):
    res = client.post("/api/v1/engine/normal/mode", json={"mode": "AUTO"})
    assert res.status_code == 403
    assert "reason" in res.json()["detail"]


def test_kill_switch_activate_without_password_allowed(client):
    res = client.post("/api/v1/risk/kill-switch", json={"active": True, "reason": "test"})
    assert res.status_code == 200
    assert res.json()["kill_switch_active"] is True
    client.app.state.trading_locks.deactivate_kill_switch()


def test_shutdown_wrong_password_not_shutdown(client):
    with patch.object(client.app.state.shutdown_manager, "shutdown", new_callable=AsyncMock) as shutdown_mock:
        res = client.post("/api/v1/system/shutdown", json={"password": "bad"})
        assert res.status_code == 403
        shutdown_mock.assert_not_awaited()


def test_shutdown_correct_password_shutdown_accepted(client):
    with patch.object(client.app.state.shutdown_manager, "shutdown", new_callable=AsyncMock) as shutdown_mock:
        res = client.post("/api/v1/system/shutdown", json={"password": DASHBOARD_PASSWORD})
        assert res.status_code == 200
        assert res.json()["status"] == "shutdown_initiated"
        shutdown_mock.assert_awaited_once_with(exit_process=True)


def test_password_never_appears_in_logs(client, caplog):
    caplog.set_level(logging.WARNING)
    secret = DASHBOARD_PASSWORD
    client.post("/api/v1/system/wakeup", json={"password": secret})
    client.post("/api/v1/system/wakeup", json={"password": "wrong"})
    assert secret not in caplog.text
