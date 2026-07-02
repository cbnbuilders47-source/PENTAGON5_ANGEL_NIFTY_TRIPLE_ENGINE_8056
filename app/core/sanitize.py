"""Sanitize broker payloads for API responses and audit logs."""

from __future__ import annotations

from typing import Any

_SAFE_TOP_KEYS = frozenset({
    "success",
    "message",
    "order_id",
    "executed_price",
    "reconciled",
})
_SAFE_STATUS_KEYS = frozenset({"status", "orderid", "averageprice", "text", "quantity"})


def sanitize_broker_response(data: dict[str, Any] | None) -> dict[str, Any]:
    """Strip raw Angel SmartAPI payloads — keep operator-relevant fields only."""
    if not data:
        return {}
    out: dict[str, Any] = {k: data[k] for k in _SAFE_TOP_KEYS if k in data}
    status = data.get("status")
    if isinstance(status, dict):
        out["status"] = {k: status[k] for k in _SAFE_STATUS_KEYS if k in status}
    elif status is not None:
        out["status"] = status
    response = data.get("response")
    if isinstance(response, dict):
        out["response_status"] = response.get("status")
        out["response_message"] = response.get("message")
    return out
