"""Angel SmartAPI live order management — LIVE ONLY."""

from __future__ import annotations

import asyncio
from typing import Any

from app.broker.angel_manager import AngelManager
from app.broker.rate_limit import RateLimitTracker
from app.core.logging import get_logger, mask_sensitive

logger = get_logger(__name__)

RETRYABLE_ERRORS = ("timeout", "network", "connection", "temporarily")


class OrderManager:
    """All live orders go through ExecutionController only."""

    def __init__(self, angel_manager: AngelManager, rate_limiter: RateLimitTracker) -> None:
        self._angel = angel_manager
        self._rate_limiter = rate_limiter

    def _api(self):
        if not self._angel.smart_api:
            raise RuntimeError("Angel session not connected")
        return self._angel.smart_api

    async def place_buy_order(
        self,
        tradingsymbol: str,
        symboltoken: str,
        exchange: str,
        quantity: int,
        producttype: str = "INTRADAY",
    ) -> dict[str, Any]:
        return await self._place_order("BUY", tradingsymbol, symboltoken, exchange, quantity, producttype)

    async def place_sell_order(
        self,
        tradingsymbol: str,
        symboltoken: str,
        exchange: str,
        quantity: int,
        producttype: str = "INTRADAY",
    ) -> dict[str, Any]:
        return await self._place_order("SELL", tradingsymbol, symboltoken, exchange, quantity, producttype)

    async def _place_order(
        self,
        transactiontype: str,
        tradingsymbol: str,
        symboltoken: str,
        exchange: str,
        quantity: int,
        producttype: str,
    ) -> dict[str, Any]:
        if self._rate_limiter.is_limited:
            return {"success": False, "message": "API rate limit active"}

        params = {
            "variety": "NORMAL",
            "tradingsymbol": tradingsymbol,
            "symboltoken": symboltoken,
            "transactiontype": transactiontype,
            "exchange": exchange,
            "ordertype": "MARKET",
            "producttype": producttype,
            "duration": "DAY",
            "quantity": str(quantity),
        }
        logger.info("Placing %s order %s qty=%s", transactiontype, mask_sensitive(tradingsymbol), quantity)

        for attempt in range(2):
            try:
                self._rate_limiter.record_call()
                response = await asyncio.to_thread(self._api().placeOrder, params)
                if response and response.get("status"):
                    order_id = response.get("data", {}).get("orderid")
                    return {"success": True, "order_id": order_id, "response": response}
                message = response.get("message", "Order failed") if response else "Empty response"
                if any(e in message.lower() for e in RETRYABLE_ERRORS) and attempt == 0:
                    await asyncio.sleep(1)
                    continue
                self._rate_limiter.record_rate_limit_error()
                return {"success": False, "message": message, "response": response}
            except Exception as exc:
                err = str(exc)
                logger.exception("Order placement error: %s", err)
                if any(e in err.lower() for e in RETRYABLE_ERRORS) and attempt == 0:
                    await asyncio.sleep(1)
                    continue
                return {"success": False, "message": err}
        return {"success": False, "message": "Order failed after retry"}

    async def get_order_book(self) -> list[dict]:
        return await self._fetch_list("orderBook")

    async def get_trade_book(self) -> list[dict]:
        return await self._fetch_list("tradeBook")

    async def get_order_status(self, order_id: str) -> dict:
        book = await self.get_order_book()
        for row in book:
            if str(row.get("orderid")) == str(order_id):
                return row
        return {}

    async def find_executed_price(self, order_id: str) -> float | None:
        trades = await self.get_trade_book()
        for row in trades:
            if str(row.get("orderid")) == str(order_id):
                return float(row.get("fillprice") or row.get("price") or 0)
        status = await self.get_order_status(order_id)
        if status:
            return float(status.get("averageprice") or status.get("price") or 0)
        return None

    async def confirm_order_execution(self, order_id: str, max_wait_sec: float = 5.0) -> dict:
        if not order_id:
            return {"success": False, "message": "No order id"}
        elapsed = 0.0
        while elapsed < max_wait_sec:
            status = await self.get_order_status(order_id)
            order_status = str(status.get("status", "")).lower()
            if order_status in ("complete", "filled"):
                price = await self.find_executed_price(order_id)
                return {"success": True, "executed_price": price, "status": status}
            if order_status in ("rejected", "cancelled"):
                return {"success": False, "message": f"Order {order_status}", "status": status}
            await asyncio.sleep(0.5)
            elapsed += 0.5
        return {"success": False, "message": "Order confirmation timeout"}

    async def reconcile_order_fill(self, order_id: str) -> dict:
        """One-shot broker reconciliation after confirm timeout."""
        if not order_id:
            return {"success": False, "message": "No order id", "reconciled": False}
        status = await self.get_order_status(order_id)
        if not status:
            return {"success": False, "message": "Order not found in order book", "reconciled": False}
        order_status = str(status.get("status", "")).lower()
        if order_status in ("complete", "filled"):
            price = await self.find_executed_price(order_id)
            return {
                "success": True,
                "executed_price": price,
                "status": status,
                "reconciled": True,
                "message": "Reconciled fill after timeout",
            }
        if order_status in ("rejected", "cancelled"):
            return {
                "success": False,
                "message": f"Order {order_status}",
                "status": status,
                "reconciled": True,
            }
        return {
            "success": False,
            "message": f"Order still {order_status or 'pending'}",
            "status": status,
            "reconciled": False,
        }

    async def _fetch_list(self, method: str) -> list[dict]:
        if self._rate_limiter.is_limited:
            return []
        try:
            self._rate_limiter.record_call()
            response = await asyncio.to_thread(getattr(self._api(), method))
            if response and response.get("status"):
                data = response.get("data", [])
                return data if isinstance(data, list) else []
        except Exception as exc:
            logger.error("%s fetch failed: %s", method, exc)
        return []
