"""Startup validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationCheck:
    name: str
    passed: bool
    message: str


@dataclass
class StartupValidation:
    valid: bool
    checks: list[ValidationCheck] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "checks": [{"name": c.name, "passed": c.passed, "message": c.message} for c in self.checks],
        }


def validate_startup() -> StartupValidation:
    settings = get_settings()
    checks = [
        _check_env_file(),
        _check_angel_credentials(settings),
        _check_port(settings),
        _check_writable(settings.data_dir, "data_dir"),
        _check_writable(settings.logs_dir, "logs_dir"),
        _check_writable(settings.reports_dir, "reports_dir"),
    ]
    valid = all(c.passed for c in checks)
    if not valid:
        logger.warning("Startup validation failed")
    return StartupValidation(valid=valid, checks=checks)


def _check_env_file() -> ValidationCheck:
    path = Path(".env")
    ok = path.exists()
    return ValidationCheck("env_file", ok, ".env present" if ok else ".env missing — copy from .env.example")


def _check_angel_credentials(settings: Settings) -> ValidationCheck:
    ok = settings.angel_configured
    return ValidationCheck("angel_credentials", ok, "Angel credentials configured" if ok else "Angel credentials incomplete")


def _check_port(settings: Settings) -> ValidationCheck:
    ok = settings.port == 8056
    return ValidationCheck("port_8056", ok, f"Port {settings.port}" if ok else f"Expected port 8056, got {settings.port}")


def _check_writable(path: Path, name: str) -> ValidationCheck:
    try:
        path.mkdir(parents=True, exist_ok=True)
        test = path / ".write_test"
        test.write_text("ok")
        test.unlink()
        return ValidationCheck(name, True, f"{name} writable")
    except Exception as exc:
        return ValidationCheck(name, False, str(exc))
