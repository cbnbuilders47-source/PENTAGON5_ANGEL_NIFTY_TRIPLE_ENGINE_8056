"""AI-assisted decision layer for engine signals."""

from __future__ import annotations

from app.core.logging import get_logger
from app.models.enums import AIRecommendation, BiasDirection

logger = get_logger(__name__)


class AIDecision:
    def evaluate(self, context: dict) -> dict:
        bias_dir = context.get("bias_direction", BiasDirection.NEUTRAL.value)
        confidence = float(context.get("bias_confidence", 0))
        mode = context.get("market_mode", "RANGE")

        if confidence < 40:
            return {"recommendation": AIRecommendation.WAIT.value, "confidence": confidence}

        if bias_dir == BiasDirection.BULL.value:
            rec = AIRecommendation.STRONG_BULL if confidence >= 75 else AIRecommendation.BULL
        elif bias_dir == BiasDirection.BEAR.value:
            rec = AIRecommendation.STRONG_BEAR if confidence >= 75 else AIRecommendation.BEAR
        else:
            rec = AIRecommendation.NEUTRAL

        if mode == "VOLATILE" and confidence < 70:
            rec = AIRecommendation.WAIT

        logger.debug("AI recommendation: %s (%.1f%%)", rec.value, confidence)
        return {"recommendation": rec.value, "confidence": confidence}
