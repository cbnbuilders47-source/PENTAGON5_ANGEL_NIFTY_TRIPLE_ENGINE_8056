"""Pydantic request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import BiasDirection, EngineStatus, SessionPhase


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str


class ReadinessResponse(BaseModel):
    ready: bool
    broker_configured: bool
    database: bool
    details: dict[str, str]


class AllocationUpdate(BaseModel):
    normal: float = Field(..., ge=0, le=100)
    wick: float = Field(..., ge=0, le=100)
    ultra: float = Field(..., ge=0, le=100)

    @field_validator("ultra")
    @classmethod
    def validate_total(cls, v: float, info) -> float:
        data = info.data
        total = data.get("normal", 0) + data.get("wick", 0) + v
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"Allocations must sum to 100%, got {total}%")
        return v


class AllocationResponse(BaseModel):
    normal: float
    wick: float
    ultra: float
    total: float = 100.0


class EngineInfo(BaseModel):
    name: str
    status: EngineStatus
    allocation_pct: float
    allocated_margin: float
    pnl: float
    open_positions: int


class BiasInfo(BaseModel):
    direction: BiasDirection
    confidence_pct: float
    locked: bool


class StateResponse(BaseModel):
    session_phase: SessionPhase
    broker_connected: bool
    websocket_connected: bool
    available_margin: float
    bias: BiasInfo
    allocations: AllocationResponse
    engines: list[EngineInfo]
    last_updated: datetime


class CandleBar(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


class CandleResponse(BaseModel):
    symbol: str
    candles: list[CandleBar]
