"""Restart recovery — rebuild positions from broker."""

from __future__ import annotations

from app.broker.order_manager import OrderManager
from app.broker.position_manager import PositionManager
from app.core.logging import get_logger
from app.core.state import AppState
from app.storage.position_store import PositionStore

logger = get_logger(__name__)

_VALID_ENGINES = frozenset({"normal", "wick", "ultra"})


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
        logger.info("Starting execution recovery")
        snapshot = self._store.load()
        orders = await self._orders.get_order_book()
        trades = await self._orders.get_trade_book()
        broker_positions = await self._positions.sync_positions()

        for eng in list(self._state.live_positions.keys()):
            self._state.clear_live_position(eng)
            if eng in self._state.engines:
                self._state.engines[eng].open_positions = 0

        open_broker = [p for p in broker_positions if _net_qty(p) != 0]
        recovered = 0
        unknown = 0
        unmatched_snapshot = set(snapshot.keys())

        for bp in open_broker:
            engine = _resolve_engine(bp, snapshot)
            if engine in _VALID_ENGINES:
                pos = _merge_position(snapshot.get(engine, {}), bp, engine)
                self._state.set_live_position(engine, pos)
                self._state.engines[engine].open_positions = 1
                unmatched_snapshot.discard(engine)
                recovered += 1
            else:
                unknown += 1
                logger.warning(
                    "Unmapped broker position: %s token=%s qty=%s",
                    bp.get("tradingsymbol"),
                    bp.get("symboltoken"),
                    _net_qty(bp),
                )

        # Snapshot without matching broker leg — stale or broker fetch failed
        if unmatched_snapshot and not open_broker and snapshot:
            unknown += len(unmatched_snapshot)
            logger.warning("Persisted snapshot has positions but broker returned none: %s", unmatched_snapshot)

        clean = unknown == 0
        status = "clean" if clean else "dirty"
        summary = {
            "orders": len(orders),
            "trades": len(trades),
            "positions_recovered": recovered,
            "unknown_positions": unknown,
            "snapshot_engines": list(snapshot.keys()),
            "broker_open_legs": len(open_broker),
            "status": status,
            "clean": clean,
            "message": "Recovery clean" if clean else f"{unknown} unknown position(s) require review",
        }
        self._state.set_recovery_summary(summary)
        self._state.set_recovery_status(summary)
        self._store.save(dict(self._state.live_positions))
        logger.info("Recovery complete: %s", summary)
        return summary


def _net_qty(pos: dict) -> int:
    try:
        return int(float(pos.get("netqty") or pos.get("quantity") or 0))
    except (TypeError, ValueError):
        return 0


def _resolve_engine(broker_pos: dict, snapshot: dict[str, dict]) -> str | None:
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
    })
    if "entry_price" not in merged and merged.get("current_ltp"):
        merged["entry_price"] = merged["current_ltp"]
    return merged
