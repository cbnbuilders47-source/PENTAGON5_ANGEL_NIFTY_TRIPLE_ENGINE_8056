"""Broker-truth validation for live orders and positions."""

from __future__ import annotations

import re
from typing import Any

# Known test/mock order IDs — must never create live positions in production.
_BLOCKED_ORDER_IDS = frozenset({"O1", "E1", "1", "12345", "order-1", "test"})

_NIFTY_OPT = re.compile(r"^NIFTY\d{2}[A-Z]{3}\d{2}(\d+)(CE|PE)$", re.IGNORECASE)


def is_valid_angel_order_id(order_id: str | None) -> bool:
    if not order_id:
        return False
    oid = str(order_id).strip()
    if not oid or oid in _BLOCKED_ORDER_IDS:
        return False
    if len(oid) < 6:
        return False
    return oid.isdigit() or (oid.isalnum() and not oid.isalpha())


def parse_nifty_option_symbol(tradingsymbol: str) -> dict[str, Any]:
    """Parse Angel NFO symbol e.g. NIFTY07JUL2624350CE."""
    sym = (tradingsymbol or "").strip().upper()
    m = _NIFTY_OPT.match(sym)
    if not m:
        return {"strike": None, "option_side": None, "expiry": None}
    return {"strike": int(m.group(1)), "option_side": m.group(2).upper(), "expiry": None}


def net_position_qty(pos: dict) -> int:
    try:
        return int(float(pos.get("netqty") or pos.get("quantity") or pos.get("buyqty") or 0))
    except (TypeError, ValueError):
        return 0


def broker_position_matches(pos: dict, *, token: str = "", tradingsymbol: str = "") -> bool:
    row_token = str(pos.get("symboltoken") or "")
    row_symbol = str(pos.get("tradingsymbol") or "").upper()
    if token and row_token == str(token):
        return net_position_qty(pos) != 0
    if tradingsymbol and row_symbol == tradingsymbol.upper():
        return net_position_qty(pos) != 0
    return False


def find_broker_open_leg(broker_positions: list[dict], token: str, tradingsymbol: str) -> dict | None:
    for bp in broker_positions:
        if broker_position_matches(bp, token=token, tradingsymbol=tradingsymbol):
            return bp
    return None


def find_complete_buy_order(orders: list[dict], token: str, tradingsymbol: str) -> dict | None:
    for row in orders:
        row_token = str(row.get("symboltoken") or "")
        row_symbol = str(row.get("tradingsymbol") or "").upper()
        if token and row_token != str(token) and tradingsymbol and row_symbol != tradingsymbol.upper():
            continue
        if not ((token and row_token == str(token)) or (tradingsymbol and row_symbol == tradingsymbol.upper())):
            continue
        tx = str(row.get("transactiontype") or "").upper()
        status = str(row.get("status") or "").lower()
        if tx == "BUY" and status in ("complete", "filled"):
            oid = row.get("orderid")
            if oid and is_valid_angel_order_id(str(oid)):
                return row
    return None


def extract_fill_details(order_row: dict, trades: list[dict], order_id: str) -> dict[str, Any]:
    """Return executed price and qty from trade book or order row."""
    filled_qty = 0
    price = 0.0
    for row in trades:
        if str(row.get("orderid")) != str(order_id):
            continue
        if str(row.get("transactiontype") or "").upper() != "BUY":
            continue
        try:
            filled_qty += int(float(row.get("fillsize") or row.get("quantity") or 0))
        except (TypeError, ValueError):
            pass
        try:
            price = float(row.get("fillprice") or row.get("price") or 0) or price
        except (TypeError, ValueError):
            pass
    if not price and order_row:
        try:
            price = float(order_row.get("averageprice") or order_row.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0
    if not filled_qty and order_row:
        try:
            filled_qty = int(float(order_row.get("filledshares") or order_row.get("quantity") or 0))
        except (TypeError, ValueError):
            filled_qty = 0
    return {"executed_price": price, "filled_qty": filled_qty}
