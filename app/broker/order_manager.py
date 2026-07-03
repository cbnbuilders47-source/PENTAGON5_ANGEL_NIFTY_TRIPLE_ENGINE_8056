"""Angel SmartAPI live order management — LIVE ONLY."""

from __future__ import annotations

import asyncio
from typing import Any

from app.broker.broker_verify import extract_fill_details, is_valid_angel_order_id
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
        safe_params = {
            "variety": params["variety"],
            "tradingsymbol": mask_sensitive(tradingsymbol),
            "symboltoken": mask_sensitive(symboltoken),
            "transactiontype": transactiontype,
            "exchange": exchange,
            "ordertype": params["ordertype"],
            "producttype": producttype,
            "duration": params["duration"],
            "quantity": quantity,
        }
        logger.info("Angel placeOrder request: %s", safe_params)

        for attempt in range(2):
            try:
                self._rate_limiter.record_call()
                response = await asyncio.to_thread(self._api().placeOrder, params)
                logger.info(
                    "Angel placeOrder raw response_type=%s preview=%s",
                    type(response).__name__,
                    mask_sensitive(str(response)[:120]),
                )
                parsed = self._parse_place_order_response(response)
                if parsed.get("success"):
                    order_id = parsed.get("order_id")
                    if not is_valid_angel_order_id(order_id):
                        return {
                            "success": False,
                            "message": "Invalid Angel order id",
                            "reason": f"placeOrder returned non-broker order id: {order_id!r}",
                            "response": response,
                        }
                    logger.info(
                        "Angel placeOrder accepted order_id=%s symbol=%s qty=%s response_type=%s",
                        order_id, mask_sensitive(tradingsymbol), quantity, type(response).__name__,
                    )
                    return parsed
                message = parsed.get("message", "Order failed")
                reason = parsed.get("reason", message)
                logger.error(
                    "Angel placeOrder failed attempt=%s reason=%s symbol=%s qty=%s response_type=%s",
                    attempt + 1, reason, mask_sensitive(tradingsymbol), quantity, type(response).__name__,
                )
                if any(e in message.lower() for e in RETRYABLE_ERRORS) and attempt == 0:
                    await asyncio.sleep(1)
                    continue
                self._rate_limiter.record_rate_limit_error()
                return {"success": False, "message": message, "reason": reason, "response": response}
            except Exception as exc:
                err = str(exc)
                logger.exception("Order placement error: %s", err)
                if any(e in err.lower() for e in RETRYABLE_ERRORS) and attempt == 0:
                    await asyncio.sleep(1)
                    continue
                return {"success": False, "message": err}
        return {"success": False, "message": "Order failed after retry"}

    @staticmethod
    def _parse_place_order_response(response: Any) -> dict[str, Any]:
        """Normalize Angel SmartAPI placeOrder responses (dict or raw order-id string)."""
        if isinstance(response, str):
            order_id = response.strip()
            if order_id:
                return {"success": True, "order_id": order_id, "response": response}
            return {"success": False, "message": "Empty response", "reason": "Angel placeOrder returned empty string", "response": response}
        if isinstance(response, dict) and response.get("status"):
            data = response.get("data") or {}
            order_id = data.get("orderid") if isinstance(data, dict) else None
            if not order_id:
                order_id = response.get("orderid") or response.get("order_id")
            return {"success": True, "order_id": str(order_id) if order_id else None, "response": response}
        message, reason = OrderManager._describe_order_failure(response)
        return {"success": False, "message": message, "reason": reason, "response": response}

    @staticmethod
    def _describe_order_failure(response: Any) -> tuple[str, str]:
        """Return operator message and detailed reason for failed placeOrder."""
        if response is None:
            return "Empty response", "Angel placeOrder returned None"
        if response is False:
            return "Empty response", "Angel placeOrder returned False"
        if not isinstance(response, dict):
            return "Empty response", f"Angel placeOrder returned {type(response).__name__}"
        if not response:
            return "Empty response", "Angel placeOrder returned empty dict"
        if not response.get("status"):
            detail = response.get("message") or response.get("errorcode") or response.get("errorCode")
            if not detail and response.get("data"):
                detail = str(response.get("data"))
            reason = f"Angel placeOrder status=False: {detail or 'no message'}"
            return detail or "Order failed", reason
        return "Order failed", "Angel placeOrder unexpected failure"

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

    async def confirm_order_execution(
        self,
        order_id: str,
        max_wait_sec: float = 5.0,
        expected_qty: int | None = None,
    ) -> dict:
        if not is_valid_angel_order_id(order_id):
            return {"success": False, "message": "Invalid order id", "reconciled": True}
        elapsed = 0.0
        while elapsed < max_wait_sec:
            status = await self.get_order_status(order_id)
            if not status:
                await asyncio.sleep(0.5)
                elapsed += 0.5
                continue
            order_status = str(status.get("status", "")).lower()
            if order_status in ("complete", "filled"):
                trades = await self.get_trade_book()
                fill = extract_fill_details(status, trades, order_id)
                price = fill.get("executed_price") or 0
                filled_qty = int(fill.get("filled_qty") or 0)
                if price <= 0:
                    return {"success": False, "message": "No executed price in Angel order book", "status": status}
                if filled_qty <= 0:
                    return {"success": False, "message": "No filled quantity in Angel order book", "status": status}
                if expected_qty and filled_qty < expected_qty:
                    return {
                        "success": False,
                        "message": f"Partial fill {filled_qty}/{expected_qty}",
                        "status": status,
                        "filled_qty": filled_qty,
                    }
                return {
                    "success": True,
                    "executed_price": price,
                    "filled_qty": filled_qty,
                    "status": status,
                }
            if order_status in ("rejected", "cancelled"):
                return {"success": False, "message": f"Order {order_status}", "status": status, "reconciled": True}
            await asyncio.sleep(0.5)
            elapsed += 0.5
        return {"success": False, "message": "Order confirmation timeout"}

    async def reconcile_order_fill(self, order_id: str, expected_qty: int | None = None) -> dict:
        """One-shot broker reconciliation after confirm timeout."""
        if not is_valid_angel_order_id(order_id):
            return {"success": False, "message": "Invalid order id", "reconciled": True}
        status = await self.get_order_status(order_id)
        if not status:
            return {"success": False, "message": "Order not found in Angel order book", "reconciled": False}
        order_status = str(status.get("status", "")).lower()
        if order_status in ("complete", "filled"):
            trades = await self.get_trade_book()
            fill = extract_fill_details(status, trades, order_id)
            price = fill.get("executed_price") or 0
            filled_qty = int(fill.get("filled_qty") or 0)
            if price <= 0 or filled_qty <= 0:
                return {
                    "success": False,
                    "message": "Order in book but fill not confirmed",
                    "status": status,
                    "reconciled": False,
                }
            if expected_qty and filled_qty < expected_qty:
                return {
                    "success": False,
                    "message": f"Partial fill {filled_qty}/{expected_qty}",
                    "status": status,
                    "reconciled": False,
                }
            return {
                "success": True,
                "executed_price": price,
                "filled_qty": filled_qty,
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
