"""Persist operator-selected engine modes across process restarts."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_settings
from app.core.constants import ENGINES
from app.core.logging import get_logger
from app.models.enums import EngineOperatingMode

logger = get_logger(__name__)

_VALID = {m.value for m in EngineOperatingMode}


class EngineModeStore:
    def __init__(self, path: Path | None = None) -> None:
        settings = get_settings()
        self._path = path or (settings.data_dir / "engine_modes.json")

    def load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            return {
                str(k): str(v)
                for k, v in data.items()
                if k in ENGINES and v in _VALID
            }
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load engine modes: %s", exc)
            return {}

    def save(self, engine_modes: dict[str, str]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {e: engine_modes[e] for e in ENGINES if e in engine_modes}
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except OSError as exc:
            logger.error("Failed to persist engine modes: %s", exc)
