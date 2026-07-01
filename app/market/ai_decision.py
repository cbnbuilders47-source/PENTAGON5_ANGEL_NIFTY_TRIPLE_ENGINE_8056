"""AI-assisted decision layer for engine signals."""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


class AIDecision:
    """Optional AI decision support — scaffold only."""

    def evaluate(self, context: dict) -> dict:
        logger.debug("AI decision evaluate pending")
        return {"signal": None, "confidence": 0.0}
