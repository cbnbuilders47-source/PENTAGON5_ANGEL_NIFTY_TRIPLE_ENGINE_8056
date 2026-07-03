"""Shared test fixtures for broker-truth order IDs."""

REAL_ORDER_ID = "240703000123456"
REAL_ORDER_ID_2 = "240703000123457"


def confirm_ok(price: float = 100.0, qty: int = 65) -> dict:
    return {"success": True, "executed_price": price, "filled_qty": qty}
