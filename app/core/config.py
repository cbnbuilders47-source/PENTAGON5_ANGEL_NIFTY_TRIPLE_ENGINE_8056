"""Application configuration via environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "PENTAGON5 ANGEL NIFTY TRIPLE ENGINE"
    app_version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8056
    debug: bool = False

    # Angel One SmartAPI (credentials from environment only)
    angel_api_key: str = ""
    angel_client_code: str = ""
    angel_password: str = ""
    angel_totp_secret: str = ""

    # SQLite persistence
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'pentagon5.db'}"

    # Paths
    data_dir: Path = PROJECT_ROOT / "data"
    logs_dir: Path = PROJECT_ROOT / "logs"
    reports_dir: Path = PROJECT_ROOT / "reports"

    # Trading constants
    lot_size: int = 65
    trading_mode: str = "LIVE"

    # Default engine capital allocation (percentages, must sum to 100)
    normal_allocation_pct: float = Field(default=30.0, ge=0, le=100)
    wick_allocation_pct: float = Field(default=30.0, ge=0, le=100)
    ultra_allocation_pct: float = Field(default=40.0, ge=0, le=100)

    # Dashboard trade confirmation (sensitive actions)
    dashboard_trade_password: str = ""

    # Session schedule (IST)
    auto_startup_time: str = "08:30:00"
    pre_market_start: str = "09:00:00"
    pre_market_end: str = "09:07:30"
    bias_lock_time: str = "09:07:31"
    trading_start_time: str = "09:15:00"
    stop_new_entries_time: str = "15:10:00"
    force_exit_time: str = "15:14:00"
    next_day_prewatch_time: str = "15:30:00"
    auto_shutdown_time: str = "16:00:00"

    @property
    def angel_configured(self) -> bool:
        return bool(
            self.angel_api_key
            and self.angel_client_code
            and self.angel_password
            and self.angel_totp_secret
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
