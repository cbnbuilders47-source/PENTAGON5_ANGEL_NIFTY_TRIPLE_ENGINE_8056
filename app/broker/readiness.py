"""Broker readiness gate — all checks must pass before live trading."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.broker.angel_manager import AngelManager
from app.broker.rate_limit import RateLimitTracker
from app.broker.token_manager import TokenManager
from app.broker.websocket_manager import WebSocketManager
from app.core.logging import get_logger
from app.core.state import AppState
from app.market.atm_manager import ATMManager
from app.market.candle_builder import CandleBuilder
from app.market.instrument_master import InstrumentMaster

logger = get_logger(__name__)

TICK_FRESHNESS_SEC = 30


@dataclass
class ReadinessCheck:
    name: str
    passed: bool
    message: str


@dataclass
class ReadinessReport:
    ready: bool
    checks: list[ReadinessCheck] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "evaluated_at": self.evaluated_at.isoformat(),
            "checks": [
                {"name": c.name, "passed": c.passed, "message": c.message}
                for c in self.checks
            ],
        }


class BrokerReadinessGate:
    """Validates broker + market data readiness (LIVE ONLY)."""

    def __init__(
        self,
        state: AppState,
        angel_manager: AngelManager,
        token_manager: TokenManager,
        websocket_manager: WebSocketManager,
        instrument_master: InstrumentMaster,
        atm_manager: ATMManager,
        candle_builder: CandleBuilder,
        rate_limiter: RateLimitTracker,
    ) -> None:
        self._state = state
        self._angel = angel_manager
        self._tokens = token_manager
        self._ws = websocket_manager
        self._instruments = instrument_master
        self._atm = atm_manager
        self._candles = candle_builder
        self._rate_limiter = rate_limiter
        self.last_report: ReadinessReport | None = None

    def evaluate(self) -> ReadinessReport:
        checks = [
            self._check_angel_connected(),
            self._check_jwt_valid(),
            self._check_feed_token_valid(),
            self._check_websocket_connected(),
            self._check_tick_fresh("NIFTY"),
            self._check_tick_fresh("ATM_CE"),
            self._check_tick_fresh("ATM_PE"),
            self._check_margin_fetched(),
            self._check_instrument_master_loaded(),
            self._check_expiry_selected(),
            self._check_no_rate_limit(),
        ]
        ready = all(c.passed for c in checks)
        report = ReadinessReport(ready=ready, checks=checks)
        self.last_report = report
        self._state.set_readiness_report(report.to_dict())
        if not ready:
            failed = [c.name for c in checks if not c.passed]
            logger.debug("Broker readiness failed: %s", ", ".join(failed))
        return report

    def _check_angel_connected(self) -> ReadinessCheck:
        ok = self._state.broker_connected and self._angel.is_connected
        return ReadinessCheck("angel_connected", ok, "Angel session active" if ok else "Angel not connected")

    def _check_jwt_valid(self) -> ReadinessCheck:
        ok = bool(self._tokens.jwt_token and self._tokens.is_valid)
        return ReadinessCheck("jwt_valid", ok, "JWT valid" if ok else "JWT missing or invalid")

    def _check_feed_token_valid(self) -> ReadinessCheck:
        ok = bool(self._tokens.feed_token)
        return ReadinessCheck("feed_token_valid", ok, "Feed token valid" if ok else "Feed token missing")

    def _check_websocket_connected(self) -> ReadinessCheck:
        ok = self._state.websocket_connected and self._ws.is_connected
        return ReadinessCheck("websocket_connected", ok, "WebSocket live" if ok else "WebSocket offline")

    def _check_tick_fresh(self, symbol: str) -> ReadinessCheck:
        last = self._candles.get_last_tick_at(symbol)
        if last is None:
            return ReadinessCheck(f"{symbol.lower()}_tick_fresh", False, f"No {symbol} ticks received")
        age = (datetime.now() - last).total_seconds()
        ok = age <= TICK_FRESHNESS_SEC
        return ReadinessCheck(
            f"{symbol.lower()}_tick_fresh",
            ok,
            f"{symbol} tick {age:.0f}s ago" if ok else f"{symbol} tick stale ({age:.0f}s)",
        )

    def _check_margin_fetched(self) -> ReadinessCheck:
        ok = self._state.available_margin > 0
        return ReadinessCheck("margin_fetched", ok, "Margin available" if ok else "Margin not fetched")

    def _check_instrument_master_loaded(self) -> ReadinessCheck:
        ok = self._instruments.is_loaded and bool(self._instruments.nifty_token)
        return ReadinessCheck("instrument_master_loaded", ok, "Instrument master loaded" if ok else "Instrument master not loaded")

    def _check_expiry_selected(self) -> ReadinessCheck:
        expiry = self._instruments.selected_expiry
        ok = bool(expiry and self._atm.ce_token and self._atm.pe_token)
        msg = f"Expiry {expiry}" if ok else "ATM expiry/tokens not resolved"
        return ReadinessCheck("expiry_selected", ok, msg)

    def _check_no_rate_limit(self) -> ReadinessCheck:
        ok = not self._rate_limiter.is_limited
        return ReadinessCheck(
            "no_rate_limit",
            ok,
            "API rate OK" if ok else "API rate-limit cooldown active",
        )
