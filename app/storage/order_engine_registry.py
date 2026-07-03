"""Map Angel order ids to engines for recovery after restart."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_settings
from app.core.constants import ENGINES
from app.core.logging import get_logger

logger = get_logger(__name__)
_MAX_ENTRIES = 500


class OrderEngineRegistry:
    def __init__(self, path: Path | None = None) -> None:
        settings = get_settings()
        self._path = path or (settings.data_dir / "order_engine_registry.json")

    def load(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load order engine registry: %s", exc)
            return {}

    def register(self, order_id: str, engine: str, tradingsymbol: str = "") -> None:
        if not order_id or engine not in ENGINES:
            return
        entries = self.load()
        entries[str(order_id)] = {
            "engine": engine,
            "tradingsymbol": tradingsymbol,
        }
        if len(entries) > _MAX_ENTRIES:
            entries = dict(list(entries.items())[-_MAX_ENTRIES:])
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except OSError as exc:
            logger.error("Failed to persist order engine registry: %s", exc)

    def resolve_engine(self, order_id: str) -> str | None:
        entry = self.load().get(str(order_id))
        if not entry:
            return None
        eng = entry.get("engine")
        return eng if eng in ENGINES else None
