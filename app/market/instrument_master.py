"""NIFTY options instrument master from Angel scrip master."""

from __future__ import annotations

import json
from datetime import date, datetime

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SCRIP_MASTER_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)


class InstrumentMaster:
    """Loads and caches NIFTY options instrument data."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._loaded = False
        self._instruments: list[dict] = []
        self.nifty_token: str = ""
        self.nifty_tradingsymbol: str = ""
        self.nifty_exchange: str = "NSE"
        self.selected_expiry: str | None = None

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def load(self) -> bool:
        cache_path = self._settings.data_dir / "OpenAPIScripMaster.json"
        self._settings.data_dir.mkdir(parents=True, exist_ok=True)

        try:
            if cache_path.exists() and cache_path.stat().st_size > 0:
                raw = cache_path.read_text(encoding="utf-8")
            else:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.get(SCRIP_MASTER_URL)
                    response.raise_for_status()
                    raw = response.text
                    cache_path.write_text(raw, encoding="utf-8")

            self._instruments = json.loads(raw)
            self._resolve_nifty_index()
            self._loaded = bool(self.nifty_token)
            if self._loaded:
                logger.info("Instrument master loaded — NIFTY token %s", self.nifty_token)
            return self._loaded
        except Exception as exc:
            logger.exception("Instrument master load failed: %s", exc)
            self._loaded = False
            return False

    def _resolve_nifty_index(self) -> None:
        for row in self._instruments:
            if (
                row.get("exch_seg") == "NSE"
                and row.get("symbol", "").upper() in {"NIFTY", "NIFTY 50", "NIFTY50"}
                and row.get("instrumenttype", "").upper() in {"AMXIDX", "INDEX", ""}
            ):
                self.nifty_token = str(row["token"])
                self.nifty_tradingsymbol = row.get("symbol", "NIFTY")
                self.nifty_exchange = "NSE"
                return

        for row in self._instruments:
            if row.get("name", "").upper() == "NIFTY" and row.get("exch_seg") == "NSE":
                self.nifty_token = str(row["token"])
                self.nifty_tradingsymbol = row.get("symbol", "NIFTY")
                self.nifty_exchange = "NSE"
                return

    def get_atm_strike(self, nifty_ltp: float) -> int:
        return int(round(nifty_ltp / 50) * 50)

    def resolve_atm_options(self, nifty_ltp: float) -> tuple[str | None, str | None]:
        if not self._loaded:
            return None, None

        strike = self.get_atm_strike(nifty_ltp)
        today = date.today()
        candidates = self._nearest_expiry_candidates(strike, today)

        ce_token = None
        pe_token = None
        for row in candidates:
            opt_type = row.get("symbol", "")[-2:].upper()
            if opt_type == "CE" and not ce_token:
                ce_token = str(row["token"])
            elif opt_type == "PE" and not pe_token:
                pe_token = str(row["token"])

        if not ce_token or not pe_token:
            for row in candidates:
                symbol = row.get("symbol", "").upper()
                if symbol.endswith("CE") and not ce_token:
                    ce_token = str(row["token"])
                elif symbol.endswith("PE") and not pe_token:
                    pe_token = str(row["token"])

        return ce_token, pe_token

    def _nearest_expiry_candidates(self, strike: int, today: date) -> list[dict]:
        rows = [
            row
            for row in self._instruments
            if row.get("name", "").upper() == "NIFTY"
            and row.get("exch_seg") == "NFO"
            and row.get("instrumenttype", "").upper() in {"OPTIDX", "OP"}
            and self._parse_strike(row) == strike
        ]
        expiries = sorted(
            {
                exp
                for row in rows
                if (exp := self._parse_expiry(row.get("expiry", ""))) is not None
                and exp >= today
            }
        )
        if not expiries:
            return rows
        nearest = expiries[0]
        self.selected_expiry = nearest.strftime("%d%b%Y").upper()
        return [row for row in rows if self._parse_expiry(row.get("expiry", "")) == nearest]

    @staticmethod
    def _parse_expiry(expiry: str) -> date | None:
        if not expiry:
            return None
        for fmt in ("%d%b%Y", "%d-%b-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(expiry.upper(), fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_strike(row: dict) -> int | None:
        strike = row.get("strike") or row.get("strikeprice")
        if strike is None:
            return None
        try:
            return int(float(strike) / 100) if float(strike) > 100000 else int(float(strike))
        except (TypeError, ValueError):
            return None
