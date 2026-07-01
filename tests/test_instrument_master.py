"""Instrument master unit tests."""

import json

import pytest

from app.core.config import Settings
from app.market.instrument_master import InstrumentMaster


@pytest.fixture
def sample_master(tmp_path):
    data = [
        {
            "token": "99926000",
            "symbol": "NIFTY",
            "name": "NIFTY",
            "exch_seg": "NSE",
            "instrumenttype": "AMXIDX",
        },
        {
            "token": "50001",
            "symbol": "NIFTY24JUL22000CE",
            "name": "NIFTY",
            "exch_seg": "NFO",
            "instrumenttype": "OPTIDX",
            "strike": "2200000",
            "expiry": "24JUL2026",
        },
        {
            "token": "50002",
            "symbol": "NIFTY24JUL22000PE",
            "name": "NIFTY",
            "exch_seg": "NFO",
            "instrumenttype": "OPTIDX",
            "strike": "2200000",
            "expiry": "24JUL2026",
        },
    ]
    cache = tmp_path / "OpenAPIScripMaster.json"
    cache.write_text(json.dumps(data), encoding="utf-8")
    settings = Settings()
    settings.data_dir = tmp_path
    return InstrumentMaster(settings), cache


@pytest.mark.asyncio
async def test_instrument_master_load(sample_master):
    master, _ = sample_master
    ok = await master.load()
    assert ok is True
    assert master.nifty_token == "99926000"


def test_resolve_atm_options(sample_master):
    master, _ = sample_master
    master._instruments = json.loads((master._settings.data_dir / "OpenAPIScripMaster.json").read_text())
    master._resolve_nifty_index()
    master._loaded = True

    ce, pe = master.resolve_atm_options(22010.0)
    assert ce == "50001"
    assert pe == "50002"
