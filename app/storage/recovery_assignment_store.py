"""Operator-assigned engine mapping for orphan broker legs."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_settings
from app.core.constants import ENGINES
from app.core.logging import get_logger

logger = get_logger(__name__)


class RecoveryAssignmentStore:
    def __init__(self, path: Path | None = None) -> None:
        settings = get_settings()
        self._path = path or (settings.data_dir / "recovery_assignments.json")

    def load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            return {str(k): str(v) for k, v in data.items() if v in ENGINES}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load recovery assignments: %s", exc)
            return {}

    def assign(self, key: str, engine: str) -> None:
        if engine not in ENGINES or not key:
            return
        entries = self.load()
        entries[str(key).upper()] = engine
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except OSError as exc:
            logger.error("Failed to persist recovery assignment: %s", exc)

    def resolve_engine(self, *, token: str = "", tradingsymbol: str = "") -> str | None:
        entries = self.load()
        for key in (tradingsymbol.upper(), token):
            if key and key in entries:
                return entries[key]
        return None
