"""Market data endpoints."""

from fastapi import APIRouter, Request

from app.core.constants import CANDLE_SYMBOLS
from app.models.schemas import CandleBar, CandleResponse

router = APIRouter()


@router.get("/bias")
async def get_bias(request: Request) -> dict:
    state = request.app.state.app_state
    return {
        "direction": state.bias_direction.value,
        "confidence_pct": state.bias_confidence_pct,
        "locked": state.bias_locked,
    }


@router.get("/candles/{symbol}", response_model=CandleResponse)
async def get_candles(request: Request, symbol: str) -> CandleResponse:
    symbol = symbol.upper()
    if symbol not in CANDLE_SYMBOLS:
        return CandleResponse(symbol=symbol, candles=[])

    candle_builder = request.app.state.candle_builder
    bars: list[CandleBar] = candle_builder.get_candles(symbol)
    return CandleResponse(symbol=symbol, candles=bars)
