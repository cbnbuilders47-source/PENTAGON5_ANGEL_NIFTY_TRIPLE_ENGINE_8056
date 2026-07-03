"""Dashboard view builders — unify widgets from live broker-truth state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.broker.broker_verify import parse_nifty_option_symbol
from app.core.state import AppState
from app.execution.execution_controller import ExecutionController


def enrich_position(pos: dict, atm_strike: int | None = None) -> dict:
    """Fill strike/side/action labels for dashboard widgets."""
    out = dict(pos)
    parsed = parse_nifty_option_symbol(str(out.get("tradingsymbol") or ""))
    if not out.get("strike") and parsed.get("strike"):
        out["strike"] = parsed["strike"]
    elif not out.get("strike") and atm_strike:
        out["strike"] = atm_strike
    if not out.get("option_side") and parsed.get("option_side"):
        out["option_side"] = parsed["option_side"]
    side = str(out.get("option_side") or "").upper()
    if side:
        out["action_label"] = f"BUY {side}"
    qty = int(out.get("quantity") or 0)
    entry = float(out.get("entry_price") or 0)
    ltp = float(out.get("current_ltp") or 0)
    if qty and entry and ltp:
        out["unrealized_pnl"] = (ltp - entry) * qty
        out["points"] = ltp - entry
    if out.get("peak_profit") is None:
        out["peak_profit"] = 0.0
    return out


def build_latest_order_view(
    state: AppState,
    exec_ctrl: ExecutionController,
    atm_strike: int | None = None,
) -> dict | None:
    """Latest Order widget — execution result or broker-confirmed live position."""
    recent = exec_ctrl.status().get("recent", [])
    if state.execution_results:
        recent = recent + state.execution_results
    for row in reversed(recent):
        if row.get("order_id") or row.get("state") in ("POSITION_ACTIVE", "ORDER_REJECTED", "EXIT_CONFIRMED"):
            enriched = dict(row)
            br = dict(enriched.get("broker_response") or {})
            for eng, pos in state.live_positions.items():
                if enriched.get("engine") == eng:
                    ep = enrich_position(pos, atm_strike)
                    br.setdefault("option_side", ep.get("option_side"))
                    br.setdefault("strike", ep.get("strike"))
                    br.setdefault("tradingsymbol", ep.get("tradingsymbol"))
                    br.setdefault("symbol", ep.get("tradingsymbol"))
            enriched["broker_response"] = br
            return enriched

    for engine, pos in state.live_positions.items():
        ep = enrich_position(pos, atm_strike)
        if not ep.get("broker_verified"):
            return {
                "request_id": None,
                "engine": engine,
                "state": "BROKER_DESYNC",
                "message": "Position not confirmed in Angel order book",
                "order_id": ep.get("entry_order_id"),
                "executed_price": ep.get("entry_price"),
                "quantity": ep.get("quantity"),
                "broker_response": {
                    "option_side": ep.get("option_side"),
                    "strike": ep.get("strike"),
                    "tradingsymbol": ep.get("tradingsymbol"),
                    "symbol": ep.get("tradingsymbol"),
                    "status": "UNVERIFIED",
                },
                "updated_at": datetime.now().isoformat(),
            }
        return {
            "request_id": None,
            "engine": engine,
            "state": "POSITION_ACTIVE",
            "message": "Live position (broker confirmed)" if ep.get("broker_verified") else "Live position",
            "order_id": ep.get("entry_order_id"),
            "executed_price": ep.get("entry_price"),
            "quantity": ep.get("quantity"),
            "broker_response": {
                "option_side": ep.get("option_side"),
                "strike": ep.get("strike"),
                "tradingsymbol": ep.get("tradingsymbol"),
                "symbol": ep.get("tradingsymbol"),
                "status": "open",
            },
            "updated_at": ep.get("entry_at") or datetime.now().isoformat(),
        }
    return None


def build_trade_log_view(state: AppState, limit: int = 50) -> list[dict]:
    """Trade Log widget — execution events + closed trades."""
    rows: list[dict] = []
    for ev in state.execution_events[-limit:]:
        rows.append({
            "at": ev.get("at"),
            "engine": ev.get("engine"),
            "event": ev.get("event"),
            "symbol": ev.get("tradingsymbol") or ev.get("symbol"),
            "side": ev.get("option_side"),
            "qty": ev.get("quantity"),
            "price": ev.get("executed_price") or ev.get("entry_price"),
            "order_id": ev.get("order_id"),
            "message": ev.get("message"),
        })
    for trade in state.trade_history[-limit:]:
        rows.append({
            "at": trade.get("closed_at"),
            "engine": trade.get("engine"),
            "event": "EXIT",
            "symbol": None,
            "side": trade.get("option_side"),
            "qty": trade.get("quantity"),
            "price": trade.get("exit_price"),
            "order_id": trade.get("exit_order_id"),
            "message": trade.get("exit_reason"),
        })
    rows.sort(key=lambda r: r.get("at") or "", reverse=True)
    return rows[:limit]


def build_enriched_live_positions(state: AppState, atm_strike: int | None = None) -> dict[str, dict]:
    return {eng: enrich_position(pos, atm_strike) for eng, pos in state.live_positions.items()}


def assess_broker_desync(
    live_positions: dict[str, dict],
    broker_positions: list[dict],
) -> dict[str, Any]:
    from app.broker.broker_verify import find_broker_open_leg, net_position_qty

    open_broker = [p for p in broker_positions if net_position_qty(p) != 0]
    issues: list[dict] = []
    for engine, pos in live_positions.items():
        token = str(pos.get("token") or "")
        symbol = str(pos.get("tradingsymbol") or "")
        leg = find_broker_open_leg(open_broker, token, symbol)
        if not leg:
            issues.append({
                "engine": engine,
                "type": "app_position_no_broker_leg",
                "tradingsymbol": symbol,
                "token": token,
                "qty": pos.get("quantity"),
            })
    broker_tokens = {str(p.get("symboltoken")) for p in open_broker}
    app_tokens = {str(p.get("token") or "") for p in live_positions.values()}
    for bp in open_broker:
        tok = str(bp.get("symboltoken") or "")
        if tok and tok not in app_tokens:
            issues.append({
                "engine": None,
                "type": "broker_leg_no_app_position",
                "tradingsymbol": bp.get("tradingsymbol"),
                "token": tok,
                "qty": net_position_qty(bp),
            })
    return {
        "desync": bool(issues),
        "critical": any(i["type"] == "app_position_no_broker_leg" for i in issues),
        "issues": issues,
        "broker_open_legs": len(open_broker),
        "app_open_positions": len(live_positions),
    }
