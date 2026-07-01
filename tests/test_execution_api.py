"""Execution and engine control API tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_execution_status(client):
    res = client.get("/api/v1/execution/status")
    assert res.status_code == 200
    data = res.json()
    assert "engine_modes" in data
    assert "pending_manual" in data


def test_engine_mode_change(client):
    res = client.post("/api/v1/engine/normal/mode", json={"mode": "MONITOR"})
    assert res.status_code == 200
    assert res.json()["mode"] == "MONITOR"


def test_engine_stop(client):
    res = client.post("/api/v1/engine/normal/stop")
    assert res.status_code == 200
    assert res.json()["status"] == "stopped"


def test_positions_endpoint(client):
    res = client.get("/api/v1/positions")
    assert res.status_code == 200


def test_orders_endpoint(client):
    res = client.get("/api/v1/orders")
    assert res.status_code == 200


def test_reports_daily(client):
    res = client.get("/api/v1/reports/daily")
    assert res.status_code == 200
    assert "path" in res.json()


def test_system_restart(client):
    res = client.post("/api/v1/system/restart")
    assert res.status_code == 200
