"""Startup validation tests."""

from app.core.startup_validator import validate_startup


def test_startup_validation_runs():
    result = validate_startup()
    assert hasattr(result, "valid")
    assert len(result.checks) >= 3
    names = [c.name for c in result.checks]
    assert "port_8056" in names
