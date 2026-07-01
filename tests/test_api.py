"""API endpoint tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "PENTAGON5" in data["app"]


def test_ready(client):
    res = client.get("/api/v1/ready")
    assert res.status_code == 200
    data = res.json()
    assert "ready" in data
    assert "database" in data


def test_dashboard_state(client):
    res = client.get("/api/v1/dashboard/state")
    assert res.status_code == 200
    data = res.json()
    assert data["allocations"]["normal"] == 30
    assert data["allocations"]["wick"] == 30
    assert data["allocations"]["ultra"] == 40


def test_allocation_validation(client):
    res = client.put(
        "/api/v1/engines/allocations",
        json={"normal": 50, "wick": 30, "ultra": 30},
    )
    assert res.status_code == 422


def test_allocation_update(client):
    res = client.put(
        "/api/v1/engines/allocations",
        json={"normal": 25, "wick": 35, "ultra": 40},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["normal"] == 25


def test_dashboard_page(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "PENTAGON5" in res.text
    assert "Connect Broker" in res.text
    assert "Normal Engine" in res.text


def test_dashboard_pnl(client):
    res = client.get("/api/v1/dashboard/pnl")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "engines" in data
    assert len(data["engines"]) == 3


def test_dashboard_logs(client):
    res = client.get("/api/v1/dashboard/logs")
    assert res.status_code == 200
    data = res.json()
    assert "lines" in data
    assert "count" in data


def test_risk_status(client):
    res = client.get("/api/v1/risk/status")
    assert res.status_code == 200
    data = res.json()
    assert "trading_allowed" in data
    assert "gates" in data


def test_scheduler_status(client):
    res = client.get("/api/v1/scheduler/status")
    assert res.status_code == 200
    data = res.json()
    assert "current_phase" in data


def test_broker_readiness(client):
    res = client.get("/api/v1/broker/readiness")
    assert res.status_code == 200
    data = res.json()
    assert "ready" in data
    assert "checks" in data
