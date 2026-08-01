"""Application settings, loaded from environment and `.env`."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

AlpacaFeed = Literal["sip", "iex"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_feed: AlpacaFeed = "sip"
    alpaca_data_url: str = "https://data.alpaca.markets"

    sec_user_agent: str = ""
    sec_tickers_url: str = "https://www.sec.gov/files/company_tickers.json"
    sec_facts_url: str = "https://data.sec.gov/api/xbrl/companyfacts"

    database_url: str = "sqlite:///./cache.db"
    risk_free_rate: float = Field(default=0.045, ge=0.0, le=1.0)

    request_timeout: float = 30.0

    @property
    def has_alpaca_credentials(self) -> bool:
        return bool(self.alpaca_api_key and self.alpaca_secret_key)

    @property
    def alpaca_headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.alpaca_api_key,
            "APCA-API-SECRET-KEY": self.alpaca_secret_key,
        }

    @property
    def sec_headers(self) -> dict[str, str]:
        # SEC returns 403 for requests that do not identify the caller.
        return {
            "User-Agent": self.sec_user_agent or "portfolio-analytics contact@example.com",
            "Accept-Encoding": "gzip, deflate",
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
