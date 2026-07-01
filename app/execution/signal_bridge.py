"""Convert engine decisions to execution signals."""

from __future__ import annotations

from app.execution.execution_models import ExecutionSignal
from app.intelligence.types import EngineDecisionSnapshot
from app.market.atm_manager import ATMManager
from app.market.candle_builder import CandleBuilder
from app.market.instrument_master import InstrumentMaster


def decision_to_signal(
    engine: str,
    snap: EngineDecisionSnapshot,
    instruments: InstrumentMaster,
    atm: ATMManager,
    candles: CandleBuilder,
) -> ExecutionSignal | None:
    if not snap.decision.startswith("WOULD_"):
        return None

    action = snap.decision.replace("WOULD_", "")
    if action == "BUY":
        ce_candles = candles.get_candles("ATM_CE")
        pe_candles = candles.get_candles("ATM_PE")
        premium_ce = ce_candles[-1].close if ce_candles else 0
        premium_pe = pe_candles[-1].close if pe_candles else 0
        option_side = "CE" if premium_ce >= premium_pe else "PE"
    elif action == "BUY_CE":
        action = "BUY"
        option_side = "CE"
    elif action == "BUY_PE":
        action = "BUY"
        option_side = "PE"
    elif action == "EXIT":
        option_side = ""
    else:
        return None

    if action == "EXIT":
        return ExecutionSignal(
            engine=engine, action="EXIT", symbol="", tradingsymbol="", token="",
            reasons=snap.reasons, confidence=snap.confidence,
            opportunity_score=snap.opportunity_score,
        )

    token = atm.ce_token if option_side == "CE" else atm.pe_token
    if not token:
        return None

    premium_candles = candles.get_candles(f"ATM_{option_side}")
    premium = premium_candles[-1].close if premium_candles else 0

    return ExecutionSignal(
        engine=engine,
        action=f"BUY_{option_side}" if option_side else action,
        symbol=f"ATM_{option_side}",
        tradingsymbol=f"NIFTY{atm.atm_strike}{option_side}",
        token=token,
        exchange="NFO",
        strike=atm.atm_strike,
        expiry=instruments.selected_expiry,
        option_side=option_side,
        premium=premium,
        confidence=snap.confidence,
        opportunity_score=snap.opportunity_score,
        reasons=snap.reasons,
        target=snap.expected_target,
        stop_loss=snap.expected_sl,
        trailing_sl=snap.trailing_sl,
    )
