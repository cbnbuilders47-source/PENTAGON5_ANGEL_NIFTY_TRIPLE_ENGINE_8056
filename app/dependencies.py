"""Shared FastAPI dependencies."""

from functools import lru_cache

from fastapi import Request

from app.core.config import Settings, get_settings
from app.core.state import AppState, get_app_state


@lru_cache
def get_cached_settings() -> Settings:
    return get_settings()


def get_state(request: Request) -> AppState:
    return request.app.state.app_state
