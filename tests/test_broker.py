"""Broker integration tests with mocked SmartAPI."""

from unittest.mock import MagicMock, patch

import pytest

from app.broker.angel_manager import AngelManager
from app.broker.margin_manager import MarginManager
from app.broker.token_manager import TokenManager
from app.core.config import Settings
from app.core.state import AppState


@pytest.fixture
def settings():
    return Settings(
        angel_api_key="test-key",
        angel_client_code="TEST123",
        angel_password="secret",
        angel_totp_secret="JBSWY3DPEHPK3PXP",
    )


@pytest.mark.asyncio
async def test_angel_login_stores_tokens(settings):
    tokens = TokenManager()
    manager = AngelManager(settings, tokens)

    mock_api = MagicMock()
    mock_api.generateSession.return_value = {
        "status": True,
        "data": {"jwtToken": "a" * 40, "refreshToken": "refresh"},
    }
    mock_api.getfeedToken.return_value = "feed-token-12345"

    with patch("SmartApi.SmartConnect", return_value=mock_api), patch(
        "pyotp.TOTP"
    ) as mock_pyotp:
        mock_pyotp.TOTP.return_value.now.return_value = "123456"
        ok = await manager.connect()

    assert ok is True
    assert tokens.is_valid
    assert manager.is_connected


@pytest.mark.asyncio
async def test_margin_fetch_updates_state(settings):
    state = AppState()
    tokens = TokenManager()
    tokens.set_tokens("j" * 30, "feed-token-12345")
    manager = AngelManager(settings, tokens)
    manager._connected = True
    manager._smart_api = MagicMock()
    manager._smart_api.rmsLimit.return_value = {
        "status": True,
        "data": {"availablecash": "150000.50", "net": "150000.50"},
    }

    margin_mgr = MarginManager(state, manager)
    margin = await margin_mgr.refresh()

    assert margin == 150000.50
    assert state.available_margin == 150000.50
    assert state.today_realized_pnl == 0.0


def test_token_manager_validation():
    tokens = TokenManager()
    assert tokens.is_valid is False
    tokens.set_tokens("x" * 25, "feed-123")
    assert tokens.is_valid is True
    tokens.clear()
    assert tokens.is_valid is False
