"""Persist live position snapshots for restart recovery."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class PositionStore:
    """JSON snapshot of engine → position dict for crash/restart recovery."""

    def __init__(self, path: Path | None = None) -> None:
        settings = get_settings()
        self._path = path or (settings.data_dir / "live_positions.json")

    def save(self, live_positions: dict[str, dict]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {engine: dict(pos) for engine, pos in live_positions.items()}
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except OSError as exc:
            logger.error("Failed to persist live positions: %s", exc)

    def load(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if isinstance(v, dict)}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load position snapshot: %s", exc)
        return {}

    def clear(self) -> None:
        try:
            if self._path.exists():
                self._path.unlink()
        except OSError as exc:
            logger.warning("Failed to clear position snapshot: %s", exc)
