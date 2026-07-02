"""Dashboard trade password verification for sensitive actions."""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request

from app.core.logging import get_logger

logger = get_logger(__name__)


def require_trade_password(request: Request, password: str | None, action: str) -> None:
    """Validate dashboard trade password. Never logs the password value."""
    settings = request.app.state.settings
    configured = (getattr(settings, "dashboard_trade_password", None) or "").strip()
    client = request.client.host if request.client else "unknown"

    if not configured:
        logger.warning(
            "Password confirmation failed — not configured | action=%s client=%s",
            action,
            client,
        )
        raise HTTPException(status_code=403, detail="Password confirmation failed")

    if not password:
        logger.warning(
            "Password confirmation failed — missing | action=%s client=%s",
            action,
            client,
        )
        raise HTTPException(status_code=403, detail="Password confirmation failed")

    if not secrets.compare_digest(password, configured):
        logger.warning(
            "Password confirmation failed — invalid | action=%s client=%s",
            action,
            client,
        )
        raise HTTPException(status_code=403, detail="Password confirmation failed")
