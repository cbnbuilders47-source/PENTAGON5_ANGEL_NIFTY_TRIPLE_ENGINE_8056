"""Structured logging for engine decisions."""

from __future__ import annotations

from datetime import datetime

from app.core.logging import get_logger
from app.intelligence.types import EngineDecisionSnapshot

logger = get_logger("app.engines.decisions")


def log_decision(snapshot: EngineDecisionSnapshot) -> None:
    ts = snapshot.updated_at.strftime("%H:%M:%S")
    header = f"{ts} | {snapshot.engine.title()} Engine | {snapshot.decision} | Phase {snapshot.phase.value}"
    reason_block = "\n".join(f"  - {r}" for r in snapshot.reasons) or "  - No reasons"
    metrics = (
        f"  Confidence {snapshot.confidence:.1f}% | "
        f"Opportunity {snapshot.opportunity_score:.1f} | "
        f"Entry Quality {snapshot.entry_quality:.1f} | "
        f"Momentum {snapshot.momentum:.1f} | "
        f"Liquidity {snapshot.liquidity:.1f} | "
        f"Health {snapshot.market_health:.1f}"
    )
    logger.info("%s\n%s\n%s", header, reason_block, metrics)
