"""WebSocket stale tick detection tests."""

from datetime import datetime, timedelta

from app.broker.websocket_manager import WebSocketManager


def test_is_stale_without_ticks():
    ws = WebSocketManager()
    assert ws.is_stale("NIFTY") is True


def test_is_fresh_with_recent_tick():
    ws = WebSocketManager()
    ws._last_tick_at["NIFTY"] = datetime.now()
    assert ws.is_stale("NIFTY") is False


def test_is_stale_with_old_tick():
    ws = WebSocketManager()
    ws._last_tick_at["NIFTY"] = datetime.now() - timedelta(seconds=60)
    assert ws.is_stale("NIFTY") is True
