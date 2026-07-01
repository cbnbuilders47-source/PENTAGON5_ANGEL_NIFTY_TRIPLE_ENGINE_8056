"""Broker readiness gate tests."""

from datetime import datetime
from unittest.mock import MagicMock

from app.broker.rate_limit import RateLimitTracker
from app.broker.readiness import BrokerReadinessGate
from app.core.state import AppState
from app.market.candle_builder import CandleBuilder


def _gate(state: AppState | None = None) -> BrokerReadinessGate:
    state = state or AppState()
    tokens = MagicMock()
    tokens.jwt_token = "x" * 30
    tokens.feed_token = "feed-token-12345"
    tokens.is_valid = True
    angel = MagicMock()
    angel.is_connected = True
    ws = MagicMock()
    ws.is_connected = True
    instruments = MagicMock()
    instruments.is_loaded = True
    instruments.nifty_token = "99926000"
    instruments.selected_expiry = "24JUL2026"
    atm = MagicMock()
    atm.ce_token = "1"
    atm.pe_token = "2"
    candles = CandleBuilder()
    candles.on_tick("NIFTY", 22000, 1, datetime.now())
    candles.on_tick("ATM_CE", 120, 1, datetime.now())
    candles.on_tick("ATM_PE", 110, 1, datetime.now())
    state.broker_connected = True
    state.websocket_connected = True
    state.available_margin = 100000
    return BrokerReadinessGate(state, angel, tokens, ws, instruments, atm, candles, RateLimitTracker())


def test_readiness_all_pass():
    gate = _gate()
    report = gate.evaluate()
    assert report.ready is True
    assert len(report.checks) == 11


def test_readiness_fails_without_margin():
    state = AppState()
    state.broker_connected = True
    state.websocket_connected = True
    tokens = MagicMock()
    tokens.jwt_token = "x" * 30
    tokens.feed_token = "feed-token-12345"
    tokens.is_valid = True
    gate = BrokerReadinessGate(
        state,
        MagicMock(is_connected=True),
        tokens,
        MagicMock(is_connected=True),
        MagicMock(is_loaded=True, nifty_token="1", selected_expiry="24JUL2026"),
        MagicMock(ce_token="1", pe_token="2"),
        CandleBuilder(),
        RateLimitTracker(),
    )
    report = gate.evaluate()
    margin_check = next(c for c in report.checks if c.name == "margin_fetched")
    assert margin_check.passed is False
    assert report.ready is False
