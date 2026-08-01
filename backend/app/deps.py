"""Dependency wiring. Providers and the cache are process-wide singletons."""

from __future__ import annotations

from functools import lru_cache

from app.cache import make_session_factory
from app.config import get_settings
from app.providers.alpaca import AlpacaProvider
from app.providers.edgar import EdgarProvider
from app.services.creditlab import CreditLabService
from app.services.filings import Filings
from app.services.market_data import MarketData
from app.services.portfolio import PortfolioService


@lru_cache
def get_session_factory():
    return make_session_factory(get_settings().database_url)


@lru_cache
def get_market_data() -> MarketData:
    return MarketData(AlpacaProvider(get_settings()), get_session_factory())


@lru_cache
def get_filings() -> Filings:
    return Filings(EdgarProvider(get_settings()), get_session_factory())


@lru_cache
def get_portfolio_service() -> PortfolioService:
    return PortfolioService(get_market_data(), get_filings(), get_settings())


@lru_cache
def get_creditlab_service() -> CreditLabService:
    return CreditLabService(get_market_data(), get_filings(), get_settings())
