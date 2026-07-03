"""Restart recovery — rebuild positions from broker."""

from __future__ import annotations

from app.broker.order_manager import OrderManager
from app.broker.position_manager import PositionManager
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.state import AppState
from app.storage.position_store import PositionStore

logger = get_logger(__name__)

_VALID_ENGINES = frozenset({"normal", "wick", "ultra"})
_AUDIT_TAIL_LINES = 500


class ExecutionRecovery:
    def __init__(
        self,
        state: AppState,
        order_manager: OrderManager,
        position_manager: PositionManager,
        position_store: PositionStore | None = None,
    ) -> None:
        self._state = state
        self._orders = order_manager
        self._positions = position_manager
        self._store = position_store or PositionStore()

    async def recover(self) -> dict:
        return await self._run_resync(clear_stale_snapshot=True)

    async def resync(self) -> dict:
        """Reconcile broker positions/order book with AppState (operator-triggered)."""
        return await self._run_resync(clear_stale_snapshot=True)

    async def _run_resync(self, *, clear_stale_snapshot: bool) -> dict:
        logger.info("Starting execution recovery/resync")
        snapshot = self._store.load()
        orders = await self._orders.get_order_book()
        trades = await self._orders.get_trade_book()
        broker_positions, positions_ok = await self._positions.sync_positions_with_status()

        for eng in list(self._state.live_positions.keys()):
            self._state.clear_live_position(eng)
            if eng in self._state.engines:
                self._state.engines[eng].open_positions = 0

        open_broker = [p for p in broker_positions if _net_qty(p) != 0]
        recovered = 0
        unknown = 0
        unknown_details: list[dict] = []
        unmatched_snapshot = set(snapshot.keys())
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

        if clear_stale_snapshot and unmatched_snapshot and not open_broker and snapshot:
            if self._state.broker_connected and positions_ok:
                logger.warning(
                    "Clearing stale position snapshot — broker confirmed flat: %s",
                    list(unmatched_snapshot),
                )
                self._store.clear()
                snapshot = {}
                unmatched_snapshot = set()
                stale_snapshot_cleared = True
            else:
                unknown += len(unmatched_snapshot)
                logger.warning(
                    "Persisted snapshot has positions but broker returned none (not clearing): %s",
                    unmatched_snapshot,
                )

        for bp in open_broker:
            engine = _resolve_engine(bp, snapshot, orders, trades, self._state.execution_results)
            if engine in _VALID_ENGINES:
                pos = _merge_position(snapshot.get(engine, {}), bp, engine)
                self._state.set_live_position(engine, pos)
                self._state.engines[engine].open_positions = 1
                unmatched_snapshot.discard(engine)
                recovered += 1
            else:
                unknown += 1
                detail = {
                    "tradingsymbol": bp.get("tradingsymbol"),
                    "token": bp.get("symboltoken"),
                    "qty": _net_qty(bp),
                }
                unknown_details.append(detail)
                logger.warning(
                    "Unmapped broker position: %s token=%s qty=%s",
                    detail["tradingsymbol"],
                    detail["token"],
                    detail["qty"],
                )

        clean = unknown == 0
        status = "clean" if clean else "dirty"
        message = "Recovery clean" if clean else f"{unknown} unknown position(s) require review"
        summary = _summary(
            orders, trades, recovered, unknown, snapshot, open_broker,
            status=status,
            message=message,
            positions_ok=positions_ok,
            stale_snapshot_cleared=stale_snapshot_cleared,
            unknown_details=unknown_details,
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
) -> dict:
    return {
        "orders": len(orders),
        "trades": len(trades),
        "positions_recovered": recovered,
        "unknown_positions": unknown,
        "unknown_details": unknown_details or [],
        "snapshot_engines": list(snapshot.keys()),
        "broker_open_legs": len(open_broker),
        "positions_fetch_ok": positions_ok,
        "stale_snapshot_cleared": stale_snapshot_cleared,
        "status": status,
        "clean": status == "clean",
        "message": message,
    }


def _net_qty(pos: dict) -> int:
    try:
        return int(float(pos.get("netqty") or pos.get("quantity") or pos.get("buyqty") or 0))
    except (TypeError, ValueError):
        return 0


def _resolve_engine(
    broker_pos: dict,
    snapshot: dict[str, dict],
    orders: list[dict],
    trades: list[dict],
    execution_results: list[dict],
) -> str | None:
    token = str(broker_pos.get("symboltoken") or "")
    symbol = str(broker_pos.get("tradingsymbol") or "")

    for engine, snap in snapshot.items():
        if token and str(snap.get("token")) == token:
            return engine
        if symbol and str(snap.get("tradingsymbol")) == symbol:
            return engine

    legacy = broker_pos.get("engine")
    if legacy in _VALID_ENGINES:
        return legacy

    from_orders = _engine_from_order_book(token, symbol, orders, execution_results)
    if from_orders:
        return from_orders

    from_trades = _engine_from_trade_book(token, symbol, trades, execution_results)
    if from_trades:
        return from_trades

    from_audit = _engine_from_execution_audit(token, symbol)
    if from_audit:
        return from_audit

    return None


def _engine_from_order_book(
    token: str,
    symbol: str,
    orders: list[dict],
    execution_results: list[dict],
) -> str | None:
    order_ids: list[str] = []
    for row in orders:
        row_token = str(row.get("symboltoken") or "")
        row_symbol = str(row.get("tradingsymbol") or "")
        if token and row_token != token and symbol and row_symbol != symbol:
            continue
        if token and row_token == token:
            pass
        elif symbol and row_symbol == symbol:
            pass
        else:
            continue
        tx = str(row.get("transactiontype") or "").upper()
        status = str(row.get("status") or "").lower()
        if tx == "BUY" and status in ("complete", "filled", "open", "trigger pending"):
            oid = row.get("orderid")
            if oid:
                order_ids.append(str(oid))

    for oid in order_ids:
        for result in reversed(execution_results):
            if str(result.get("order_id") or "") == oid:
                eng = result.get("engine")
                if eng in _VALID_ENGINES:
                    return eng

    engines: set[str] = set()
    for oid in order_ids:
        eng = _engine_from_audit_order_id(oid)
        if eng:
            engines.add(eng)
    if len(engines) == 1:
        return engines.pop()
    return None


def _engine_from_trade_book(
    token: str,
    symbol: str,
    trades: list[dict],
    execution_results: list[dict],
) -> str | None:
    order_ids: list[str] = []
    for row in trades:
        row_token = str(row.get("symboltoken") or "")
        row_symbol = str(row.get("tradingsymbol") or "")
        if token and row_token != token and symbol and row_symbol != symbol:
            continue
        if not ((token and row_token == token) or (symbol and row_symbol == symbol)):
            continue
        tx = str(row.get("transactiontype") or "").upper()
        if tx != "BUY":
            continue
        oid = row.get("orderid")
        if oid:
            order_ids.append(str(oid))

    for oid in order_ids:
        for result in reversed(execution_results):
            if str(result.get("order_id") or "") == oid:
                eng = result.get("engine")
                if eng in _VALID_ENGINES:
                    return eng

    engines: set[str] = set()
    for oid in order_ids:
        eng = _engine_from_audit_order_id(oid)
        if eng:
            engines.add(eng)
    if len(engines) == 1:
        return engines.pop()
    return None


def _engine_from_execution_audit(token: str, symbol: str) -> str | None:
    engines: set[str] = set()
    audit_path = get_settings().logs_dir / "execution_audit.log"
    if not audit_path.exists():
        return None
    try:
        lines = audit_path.read_text(encoding="utf-8", errors="replace").splitlines()[-_AUDIT_TAIL_LINES:]
    except OSError:
        return None

    for line in reversed(lines):
        if "7_place_buy_order_call" not in line:
            continue
        if token and f"'token': '{token}'" not in line and f'"token": "{token}"' not in line:
            if symbol and symbol not in line:
                continue
        if symbol and symbol not in line:
            continue
        eng = _extract_audit_field(line, "engine")
        if eng in _VALID_ENGINES:
            engines.add(eng)

    if len(engines) == 1:
        return engines.pop()
    return None


def _engine_from_audit_order_id(order_id: str) -> str | None:
    audit_path = get_settings().logs_dir / "execution_audit.log"
    if not audit_path.exists():
        return None
    try:
        lines = audit_path.read_text(encoding="utf-8", errors="replace").splitlines()[-_AUDIT_TAIL_LINES:]
    except OSError:
        return None
    for line in reversed(lines):
        if order_id not in line:
            continue
        eng = _extract_audit_field(line, "engine")
        if eng in _VALID_ENGINES:
            return eng
    return None


def _extract_audit_field(line: str, field: str) -> str | None:
    for quote in ("'", '"'):
        needle = f"{quote}{field}{quote}: {quote}"
        idx = line.find(needle)
        if idx >= 0:
            start = idx + len(needle)
            end = line.find(quote, start)
            if end > start:
                return line[start:end]
    return None


def _merge_position(snapshot: dict, broker_pos: dict, engine: str) -> dict:
    qty = abs(_net_qty(broker_pos))
    ltp = broker_pos.get("ltp") or broker_pos.get("close") or snapshot.get("current_ltp")
    merged = dict(snapshot) if snapshot else {}
    merged.update({
        "engine": engine,
        "tradingsymbol": broker_pos.get("tradingsymbol") or merged.get("tradingsymbol", ""),
        "token": str(broker_pos.get("symboltoken") or merged.get("token", "")),
        "exchange": broker_pos.get("exchange") or merged.get("exchange", "NFO"),
        "quantity": qty or merged.get("quantity", 0),
        "current_ltp": float(ltp) if ltp else float(merged.get("current_ltp") or merged.get("entry_price") or 0),
        "recovered": True,
    })
    if "entry_price" not in merged and merged.get("current_ltp"):
        merged["entry_price"] = merged["current_ltp"]
    return merged
