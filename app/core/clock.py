"""Trading session clock — always evaluate IST regardless of host timezone."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def trading_now() -> datetime:
    """Current IST as naive datetime (compatible with existing time() comparisons)."""
    return datetime.now(IST).replace(tzinfo=None)
