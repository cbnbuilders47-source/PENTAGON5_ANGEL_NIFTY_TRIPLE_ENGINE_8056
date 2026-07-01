"""Quantity calculation tests."""

from app.execution.quantity import calculate_lots


def test_calculate_lots_basic():
    lots, qty = calculate_lots(allocated_margin=50000, premium=50, available_margin=100000)
    assert lots == 15
    assert qty == 15 * 65


def test_calculate_lots_zero_premium():
    lots, qty = calculate_lots(10000, 0, 10000)
    assert lots == 0
    assert qty == 0


def test_calculate_lots_respects_available_margin():
    lots, qty = calculate_lots(allocated_margin=100000, premium=100, available_margin=6500)
    assert lots == 1
    assert qty == 65


def test_calculate_lots_low_premium():
    lots, qty = calculate_lots(allocated_margin=10000, premium=15, available_margin=10000)
    assert lots >= 1
    assert qty == lots * 65


def test_calculate_lots_max_cap():
    lots, qty = calculate_lots(allocated_margin=100000, premium=50, available_margin=100000, max_lots=2)
    assert lots == 2
    assert qty == 130
