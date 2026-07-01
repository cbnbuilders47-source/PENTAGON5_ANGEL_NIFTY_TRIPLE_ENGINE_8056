"""Available margin management — auto-fetched from Angel after login."""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.state import AppState

logger = get_logger(__name__)


class MarginManager:
    """Fetches and tracks available margin from Angel One."""

    def __init__(self, state: AppState) -> None:
        self._state = state

    async def refresh(self) -> float:
        """Fetch latest available margin via REST. Placeholder until live integration."""
        logger.debug("Margin refresh requested — live integration pending")
        return self._state.available_margin
