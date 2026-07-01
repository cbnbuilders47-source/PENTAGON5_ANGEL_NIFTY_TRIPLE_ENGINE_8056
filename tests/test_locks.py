"""Trading locks tests."""

from app.risk.locks import TradingLocks


def test_duplicate_signal_blocked():
    locks = TradingLocks()
    assert locks.register_duplicate_signal("abc") is False
    assert locks.register_duplicate_signal("abc") is True


def test_kill_switch():
    locks = TradingLocks()
    assert locks.kill_switch_active is False
    locks.activate_kill_switch()
    assert locks.kill_switch_active is True
    locks.deactivate_kill_switch()
    assert locks.kill_switch_active is False


def test_engine_and_symbol_halt():
    locks = TradingLocks()
    locks.halt_engine("normal")
    locks.halt_symbol("ATM_CE")
    assert locks.is_engine_halted("normal")
    assert locks.is_symbol_halted("ATM_CE")
