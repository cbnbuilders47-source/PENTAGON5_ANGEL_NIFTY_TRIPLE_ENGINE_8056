"""Trading and session constants."""

from datetime import time

# NIFTY options
SYMBOL = "NIFTY"
EXCHANGE = "NFO"
UNDERLYING_EXCHANGE = "NSE"
LOT_SIZE = 65

# Engine names
ENGINE_NORMAL = "normal"
ENGINE_WICK = "wick"
ENGINE_ULTRA = "ultra"

ENGINES = (ENGINE_NORMAL, ENGINE_WICK, ENGINE_ULTRA)

DEFAULT_ALLOCATIONS = {
    ENGINE_NORMAL: 30.0,
    ENGINE_WICK: 30.0,
    ENGINE_ULTRA: 40.0,
}

# Session schedule (IST)
AUTO_STARTUP = time(8, 30, 0)
PRE_MARKET_START = time(9, 0, 0)
PRE_MARKET_END = time(9, 7, 30)
BIAS_LOCK = time(9, 7, 31)
TRADING_START = time(9, 15, 0)
STOP_NEW_ENTRIES = time(15, 10, 0)
FORCE_EXIT = time(15, 14, 0)
NEXT_DAY_PREWATCH = time(15, 30, 0)
AUTO_SHUTDOWN = time(16, 0, 0)

# Candle intervals
CANDLE_INTERVAL_1M = "1m"

# Dashboard instruments for live candles
CANDLE_SYMBOLS = ("NIFTY", "ATM_CE", "ATM_PE")
