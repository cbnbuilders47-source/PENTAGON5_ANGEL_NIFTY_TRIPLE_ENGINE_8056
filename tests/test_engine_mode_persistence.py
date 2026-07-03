"""Engine mode persistence and AppState singleton tests."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.core.state import get_app_state
from app.main import create_app
from app.models.enums import SessionPhase
from app.storage.engine_mode_store import EngineModeStore


def test_engine_mode_persists_across_api_roundtrip():
    app = create_app()
    with TestClient(app) as client:
        state = client.app.state.app_state
        ctrl = client.app.state.execution_controller
        assert id(state) == id(ctrl._state)

        state.supervised_auto_enabled = True
        state.set_recovery_status({"status": "clean", "clean": True, "message": "ok"})
        state.apply_scheduler_status(MagicMock(
            current_phase=SessionPhase.TRADING,
            bias_locked=True,
            new_entries_allowed=True,
            force_exit_active=False,
        ))

        res = client.post("/api/v1/engine/wick/mode", json={"mode": "MANUAL"})
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["mode"] == "MANUAL"
        assert data["engine_modes"]["wick"] == "MANUAL"
        assert data["state_id"] == id(state)

        state_res = client.get("/api/v1/dashboard/state")
        assert state_res.status_code == 200
        assert state_res.json()["engine_modes"]["wick"] == "MANUAL"

        exec_res = client.get("/api/v1/execution/status")
        assert exec_res.json()["engine_modes"]["wick"] == "MANUAL"


def test_engine_mode_store_roundtrip(tmp_path):
    store = EngineModeStore(path=tmp_path / "engine_modes.json")
    store.save({"normal": "MONITOR", "wick": "AUTO", "ultra": "MONITOR"})
    assert store.load()["wick"] == "AUTO"

    state = get_app_state()
    state.hydrate_engine_modes(store.load())
    assert state.engine_modes["wick"] == "AUTO"
