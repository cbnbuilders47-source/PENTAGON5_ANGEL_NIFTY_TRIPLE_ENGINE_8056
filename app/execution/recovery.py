"""Restart recovery — rebuild positions from broker."""

from __future__ import annotations

from app.broker.order_manager import OrderManager
from app.broker.position_manager import PositionManager
from app.core.logging import get_logger
from app.core.state import AppState

logger = get_logger(__name__)


class ExecutionRecovery:
    def __init__(
        self,
        state: AppState,
        order_manager: OrderManager,
        position_manager: PositionManager,
    ) -> None:
        self._state = state
        self._orders = order_manager
        self._positions = position_manager

    async def recover(self) -> dict:
        logger.info("Starting execution recovery")
        orders = await self._orders.get_order_book()
        trades = await self._orders.get_trade_book()
        positions = await self._positions.sync_positions()

        recovered = 0
        for pos in positions:
            engine = pos.get("engine", "unknown")
            if engine in self._state.engines:
                self._state.set_live_position(engine, pos)
                self._state.engines[engine].open_positions = 1
                recovered += 1

        summary = {
            "orders": len(orders),
            "trades": len(trades),
            "positions_recovered": recovered,
        }
        self._state.set_recovery_summary(summary)
        logger.info("Recovery complete: %s", summary)
        return summary
