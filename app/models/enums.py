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


class EnginePhase(str, Enum):
    IDLE = "IDLE"
    READY = "READY"
    WAIT_CONFIRMATION = "WAIT_CONFIRMATION"
    ENTRY_READY = "ENTRY_READY"
    POSITION_ACTIVE = "POSITION_ACTIVE"
    EXIT_READY = "EXIT_READY"
    COMPLETED = "COMPLETED"
    RESET = "RESET"


class NormalDecision(str, Enum):
    READY = "READY"
    WAIT = "WAIT"
    BLOCKED = "BLOCKED"
    WOULD_BUY_CE = "WOULD_BUY_CE"
    WOULD_BUY_PE = "WOULD_BUY_PE"
    WOULD_EXIT = "WOULD_EXIT"


class WickDecision(str, Enum):
    READY = "READY"
    WAIT = "WAIT"
    WOULD_BUY = "WOULD_BUY"
    WOULD_EXIT = "WOULD_EXIT"


class UltraDecision(str, Enum):
    READY = "READY"
    WAIT = "WAIT"
    WOULD_BUY = "WOULD_BUY"
    WOULD_EXIT = "WOULD_EXIT"


class MarketMode(str, Enum):
    TRENDING = "TRENDING"
    RANGE = "RANGE"
    REVERSAL = "REVERSAL"
    BREAKOUT = "BREAKOUT"
    VOLATILE = "VOLATILE"
    SLOW_TREND = "SLOW_TREND"


class AIRecommendation(str, Enum):
    STRONG_BULL = "STRONG_BULL"
    BULL = "BULL"
    NEUTRAL = "NEUTRAL"
    BEAR = "BEAR"
    STRONG_BEAR = "STRONG_BEAR"
    WAIT = "WAIT"


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
