"""Pydantic enums for domain models."""

from enum import Enum


class BiasDirection(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    NEUTRAL = "NEUTRAL"


class EngineStatus(str, Enum):
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class SessionPhase(str, Enum):
    OFFLINE = "OFFLINE"
    PRE_MARKET = "PRE_MARKET"
    BIAS_LOCKED = "BIAS_LOCKED"
    TRADING = "TRADING"
    NO_NEW_ENTRIES = "NO_NEW_ENTRIES"
    FORCE_EXIT = "FORCE_EXIT"
    PREWATCH = "PREWATCH"
    SHUTDOWN = "SHUTDOWN"


class TradingMode(str, Enum):
    LIVE = "LIVE"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
