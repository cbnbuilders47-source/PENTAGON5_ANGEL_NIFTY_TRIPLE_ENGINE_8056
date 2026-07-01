"""Positions, orders, trades endpoints."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/positions")
async def get_positions(request: Request) -> dict:
    state = request.app.state.app_state
    synced = await request.app.state.position_manager.sync_positions()
    return {"live": state.live_positions, "broker": synced}


@router.get("/orders")
async def get_orders(request: Request) -> dict:
    orders = await request.app.state.order_manager.get_order_book()
    return {"orders": orders}


@router.get("/trades")
async def get_trades(request: Request) -> dict:
    trades = await request.app.state.order_manager.get_trade_book()
    history = request.app.state.app_state.trade_history
    return {"trades": trades, "history": history[-50:]}
