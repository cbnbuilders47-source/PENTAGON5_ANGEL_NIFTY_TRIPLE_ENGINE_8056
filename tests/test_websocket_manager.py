"""WebSocket tick routing tests."""

from app.broker.websocket_manager import WebSocketManager


def test_process_tick_routes_to_symbol():
    ws = WebSocketManager()
    received = []

    ws._token_to_symbol = {"99926000": "NIFTY"}
    ws._on_tick = lambda symbol, price, volume: received.append((symbol, price, volume))

    ws._process_tick({"token": "99926000", "last_traded_price": 2201050, "last_traded_quantity": 1})

    assert received == [("NIFTY", 22010.50, 1)]


def test_build_token_list_groups_by_exchange():
    ws = WebSocketManager()
    token_list = ws._build_token_list(
        {
            "NIFTY": ("NSE", "99926000"),
            "ATM_CE": ("NFO", "50001"),
            "ATM_PE": ("NFO", "50002"),
        }
    )
    assert {"exchangeType": 1, "tokens": ["99926000"]} in token_list
    nfo = next(item for item in token_list if item["exchangeType"] == 2)
    assert set(nfo["tokens"]) == {"50001", "50002"}
