"""Restart recovery — rebuild positions from broker truth only."""

from __future__ import annotations

import re

from app.broker.broker_verify import (
    extract_fill_details,
    find_broker_open_leg,
    find_complete_buy_order,
    net_position_qty,
    parse_nifty_option_symbol,
)
from app.broker.order_manager import OrderManager
from app.broker.position_manager import PositionManager
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.state import AppState
from app.dashboard.sync import assess_broker_desync
from app.storage.order_engine_registry import OrderEngineRegistry
from app.storage.position_store import PositionStore
from app.storage.recovery_assignment_store import RecoveryAssignmentStore

logger = get_logger(__name__)

_VALID_ENGINES = frozenset({"normal", "wick", "ultra"})


class ExecutionRecovery:
    def __init__(
        self,
        state: AppState,
        order_manager: OrderManager,
        position_manager: PositionManager,
        position_store: PositionStore | None = None,
        order_registry: OrderEngineRegistry | None = None,
        assignment_store: RecoveryAssignmentStore | None = None,
    ) -> None:
        self._state = state
        self._orders = order_manager
        self._positions = position_manager
        self._store = position_store or PositionStore()
        self._order_registry = order_registry or OrderEngineRegistry()
        self._assignments = assignment_store or RecoveryAssignmentStore()

    async def recover(self) -> dict:
        return await self._run_resync(clear_stale_snapshot=True)

    async def resync(self) -> dict:
        """Reconcile broker positions/order book with AppState (operator-triggered)."""
        return await self._run_resync(clear_stale_snapshot=True)

    async def _run_resync(self, *, clear_stale_snapshot: bool) -> dict:
        logger.info("Starting execution recovery/resync (broker-truth)")
        snapshot = self._store.load()
        orders = await self._orders.get_order_book()
        trades = await self._orders.get_trade_book()
        broker_positions, positions_ok = await self._positions.sync_positions_with_status()

        open_broker = [p for p in broker_positions if net_position_qty(p) != 0]
        recovered = 0
        unknown = 0
        unknown_details: list[dict] = []
        cleared_engines: list[str] = []
        stale_snapshot_cleared = False

        if not positions_ok and self._state.broker_connected:
            summary = _summary(
                orders, trades, recovered, unknown, snapshot, open_broker,
                status="dirty",
                message="Broker position fetch failed — cannot confirm flat book",
                positions_ok=False,
            )
            self._apply_summary(summary)
            return summary

        # Clear app positions with no matching broker leg (Angel is source of truth).
        for eng in list(self._state.live_positions.keys()):
            pos = self._state.live_positions[eng]
            token = str(pos.get("token") or "")
            symbol = str(pos.get("tradingsymbol") or "")
            if not find_broker_open_leg(open_broker, token, symbol):
                logger.warning(
                    "Clearing app position %s — no broker leg for %s token=%s",
                    eng, symbol, token,
                )
                self._state.clear_live_position(eng)
                if eng in self._state.engines:
                    self._state.engines[eng].open_positions = 0
                cleared_engines.append(eng)

        unmatched_snapshot = set(snapshot.keys())

        if clear_stale_snapshot and unmatched_snapshot and not open_broker and snapshot:
            if self._state.broker_connected and positions_ok:
                logger.warning("Clearing stale snapshot — broker confirmed flat: %s", list(unmatched_snapshot))
                self._store.clear()
                snapshot = {}
                unmatched_snapshot = set()
                stale_snapshot_cleared = True

        for bp in open_broker:
            token = str(bp.get("symboltoken") or "")
            symbol = str(bp.get("tradingsymbol") or "")
            engine = _resolve_engine(
                bp, snapshot, orders, trades, self._state.execution_results,
                order_registry=self._order_registry,
                assignment_store=self._assignments,
            )
            buy_order = find_complete_buy_order(orders, token, symbol)
            if engine not in _VALID_ENGINES:
                unknown += 1
                unknown_details.append({
                    "tradingsymbol": symbol,
                    "token": token,
                    "qty": net_position_qty(bp),
                    "reason": "unmapped_engine",
                })
                logger.warning("Unmapped broker position: %s token=%s qty=%s", symbol, token, net_position_qty(bp))
                continue
            if not buy_order:
                unknown += 1
                unknown_details.append({
                    "tradingsymbol": symbol,
                    "token": token,
                    "qty": net_position_qty(bp),
                    "reason": "no_confirmed_buy_order",
                })
                logger.warning(
                    "Broker leg without confirmed BUY order — not recovering: %s token=%s",
                    symbol, token,
                )
                continue

            order_id = str(buy_order.get("orderid"))
            fill = extract_fill_details(buy_order, trades, order_id)
            if float(fill.get("executed_price") or 0) <= 0 or int(fill.get("filled_qty") or 0) <= 0:
                unknown += 1
                unknown_details.append({
                    "tradingsymbol": symbol,
                    "token": token,
                    "qty": net_position_qty(bp),
                    "reason": "unconfirmed_fill",
                })
                continue

            pos = _merge_position(
                snapshot.get(engine, {}),
                bp,
                engine,
                order_id=order_id,
                entry_price=float(fill["executed_price"]),
            )
            self._state.set_live_position(engine, pos)
            self._state.engines[engine].open_positions = 1
            unmatched_snapshot.discard(engine)
            recovered += 1
            self._state.append_execution_event(
                "RECOVER",
                engine,
                tradingsymbol=symbol,
                token=token,
                quantity=pos.get("quantity"),
                executed_price=pos.get("entry_price"),
                order_id=order_id,
                message="Broker-confirmed recovery",
            )

        desync = assess_broker_desync(self._state.live_positions, broker_positions)
        self._state.set_broker_desync(desync)

        clean = unknown == 0 and not desync.get("critical")
        status = "clean" if clean else "dirty"
        message = "Recovery clean" if clean else f"{unknown} broker issue(s) require review"
        if desync.get("critical"):
            message = "Broker/app position desync — review required"

        summary = _summary(
            orders, trades, recovered, unknown, snapshot, open_broker,
            status=status,
            message=message,
            positions_ok=positions_ok,
            stale_snapshot_cleared=stale_snapshot_cleared,
            unknown_details=unknown_details,
            cleared_engines=cleared_engines,
            broker_desync=desync,
        )
        self._apply_summary(summary)
        logger.info("Recovery complete: %s", summary)
        return summary

    def _apply_summary(self, summary: dict) -> None:
        self._state.set_recovery_summary(summary)
        self._state.set_recovery_status(summary)
        self._store.save(dict(self._state.live_positions))


def _summary(
    orders: list,
    trades: list,
    recovered: int,
    unknown: int,
    snapshot: dict,
    open_broker: list,
    *,
    status: str,
    message: str,
    positions_ok: bool = True,
    stale_snapshot_cleared: bool = False,
    unknown_details: list | None = None,
    cleared_engines: list | None = None,
    broker_desync: dict | None = None,
) -> dict:
    return {
        "orders": len(orders),
        "trades": len(trades),
        "positions_recovered": recovered,
        "unknown_positions": unknown,
        "unknown_details": unknown_details or [],
        "cleared_engines": cleared_engines or [],
        "snapshot_engines": list(snapshot.keys()),
        "broker_open_legs": len(open_broker),
        "positions_fetch_ok": positions_ok,
        "stale_snapshot_cleared": stale_snapshot_cleared,
        "broker_desync": broker_desync or {},
        "status": status,
        "clean": status == "clean",
        "message": message,
    }


def _resolve_engine(
    broker_pos: dict,
    snapshot: dict[str, dict],
    orders: list[dict],
    trades: list[dict],
    execution_results: list[dict],
    *,
    order_registry: OrderEngineRegistry | None = None,
    assignment_store: RecoveryAssignmentStore | None = None,
) -> str | None:
    token = str(broker_pos.get("symboltoken") or "")
    symbol = str(broker_pos.get("tradingsymbol") or "")

    if assignment_store:
        assigned = assignment_store.resolve_engine(token=token, tradingsymbol=symbol)
        if assigned in _VALID_ENGINES:
            return assigned

    for engine, snap in snapshot.items():
        if token and str(snap.get("token")) == token:
            return engine
        if symbol and str(snap.get("tradingsymbol")) == symbol:
            return engine

    legacy = broker_pos.get("engine")
    if legacy in _VALID_ENGINES:
        return legacy

    buy = find_complete_buy_order(orders, token, symbol)
    if buy:
        oid = str(buy.get("orderid"))
        if order_registry:
            reg_engine = order_registry.resolve_engine(oid)
            if reg_engine in _VALID_ENGINES:
                return reg_engine
        for result in reversed(execution_results):
            if str(result.get("order_id") or "") == oid:
                eng = result.get("engine")
                if eng in _VALID_ENGINES:
                    return eng
        audit_engine = _engine_from_audit_log(oid=oid, tradingsymbol=symbol)
        if audit_engine in _VALID_ENGINES:
            return audit_engine

    for trade in reversed(trades):
        row_symbol = str(trade.get("tradingsymbol") or "").upper()
        row_token = str(trade.get("symboltoken") or "")
        if symbol and row_symbol != symbol.upper() and token and row_token != token:
            continue
        if not ((symbol and row_symbol == symbol.upper()) or (token and row_token == token)):
            continue
        if str(trade.get("transactiontype") or "").upper() != "BUY":
            continue
        oid = str(trade.get("orderid") or "")
        if not oid:
            continue
        if order_registry:
            reg_engine = order_registry.resolve_engine(oid)
            if reg_engine in _VALID_ENGINES:
                return reg_engine
        for result in reversed(execution_results):
            if str(result.get("order_id") or "") == oid:
                eng = result.get("engine")
                if eng in _VALID_ENGINES:
                    return eng
        audit_engine = _engine_from_audit_log(oid=oid, tradingsymbol=symbol)
        if audit_engine in _VALID_ENGINES:
            return audit_engine

    return _engine_from_audit_log(tradingsymbol=symbol)


def _engine_from_audit_log(*, oid: str = "", tradingsymbol: str = "") -> str | None:
    """Best-effort engine inference from execution_audit.log."""
    if not oid and not tradingsymbol:
        return None
    settings = get_settings()
    audit_path = settings.logs_dir / "execution_audit.log"
    if not audit_path.exists():
        return None
    symbol_key = tradingsymbol.upper()
    try:
        lines = audit_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-4000:]
    except OSError:
        return None
    for line in reversed(lines):
        if oid and oid not in line:
            if symbol_key and symbol_key not in line.upper():
                continue
        elif symbol_key and symbol_key not in line.upper():
            continue
        if "'engine':" not in line and '"engine":' not in line:
            continue
        match = re.search(r"['\"]engine['\"]\s*:\s*['\"](\w+)['\"]", line)
        if not match:
            continue
        eng = match.group(1)
        if eng in _VALID_ENGINES:
            if oid and oid in line:
                return eng
            if symbol_key and symbol_key in line.upper() and "exec_pipeline" in line:
                return eng
            if symbol_key and symbol_key in line.upper() and "POSITION_ACTIVE" in line:
                return eng
    return None


def _merge_position(
    snapshot: dict,
    broker_pos: dict,
    engine: str,
    *,
    order_id: str,
    entry_price: float,
) -> dict:
    qty = abs(net_position_qty(broker_pos))
    ltp = broker_pos.get("ltp") or broker_pos.get("close") or entry_price
    symbol = str(broker_pos.get("tradingsymbol") or snapshot.get("tradingsymbol") or "")
    parsed = parse_nifty_option_symbol(symbol)
    merged = dict(snapshot) if snapshot else {}
    merged.update({
        "engine": engine,
        "tradingsymbol": symbol,
        "token": str(broker_pos.get("symboltoken") or merged.get("token", "")),
        "exchange": broker_pos.get("exchange") or merged.get("exchange", "NFO"),
        "quantity": qty or merged.get("quantity", 0),
        "entry_price": entry_price,
        "current_ltp": float(ltp) if ltp else entry_price,
        "entry_order_id": order_id,
        "broker_verified": True,
        "recovered": True,
        "peak_profit": float(merged.get("peak_profit") or 0),
        "option_side": merged.get("option_side") or parsed.get("option_side"),
        "strike": merged.get("strike") or parsed.get("strike"),
        "entry_at": merged.get("entry_at"),
    })
    return merged
