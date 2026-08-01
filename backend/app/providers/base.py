"""Provider interfaces and shared errors.

Everything that touches the network lives behind one of these protocols, so the
analytics core never imports a client and swapping a data source is a config
change rather than a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd

from app.analytics.credit import Financials, ZVariant


class ProviderError(RuntimeError):
    """Base class for all data-source failures."""


class SymbolNotFound(ProviderError):
    """The provider has no record of this ticker."""


class RateLimited(ProviderError):
    """The provider asked us to slow down."""


class SubscriptionError(ProviderError):
    """The account's plan does not cover the requested data."""


class InsufficientData(ProviderError):
    """The provider responded, but with too little data to compute anything."""


# SIC divisions, per the SEC's own classification. Altman fitted separate
# coefficient sets for manufacturers and everyone else, and his ratios break
# down entirely for financials, so the filer's SIC code determines which
# variant is appropriate rather than leaving it to the user to guess.
_SIC_MANUFACTURING = range(2000, 4000)
_SIC_FINANCE = range(6000, 6800)


def z_variant_for_sic(sic: int | str | None) -> ZVariant | None:
    """Pick the Z-Score variant a filer's SIC code calls for.

    Returns ``None`` for financials, where the model does not apply at all.
    """
    if sic is None or sic == "":
        return "non_manufacturer"
    try:
        code = int(sic)
    except (TypeError, ValueError):
        return "non_manufacturer"

    if code in _SIC_FINANCE:
        return None
    if code in _SIC_MANUFACTURING:
        return "public_manufacturer"
    return "non_manufacturer"


@dataclass(frozen=True)
class CompanyProfile:
    symbol: str
    name: str
    cik: str
    sic: str | None = None
    sic_description: str | None = None
    shares_outstanding: float | None = None

    @property
    def z_variant(self) -> ZVariant | None:
        return z_variant_for_sic(self.sic)

    @property
    def is_financial(self) -> bool:
        return self.z_variant is None


@dataclass(frozen=True)
class AnnualFinancials:
    """A filer's figures for one fiscal year, plus provenance."""

    fiscal_year: int
    period_end: date
    financials: Financials
    form: str
    # "point_in_time" (cover-page count) or "weighted_average" (EPS denominator).
    # None when no share count could be resolved at all. Surface this: a market
    # cap built on an annual average is an approximation and should say so.
    shares_source: str | None = None

    @property
    def shares_are_approximate(self) -> bool:
        return self.shares_source == "weighted_average"


@runtime_checkable
class PriceProvider(Protocol):
    """Historical and latest equity prices."""

    def get_daily_closes(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Adjusted daily closes, indexed by date with one column per symbol."""
        ...

    def get_latest_prices(self, symbols: list[str]) -> pd.Series:
        """Most recent available price per symbol."""
        ...


@runtime_checkable
class FundamentalsProvider(Protocol):
    """Company profile and annual financial statements."""

    def get_profile(self, symbol: str) -> CompanyProfile: ...

    def get_annual_financials(
        self,
        symbol: str,
        years: int = 2,
    ) -> list[AnnualFinancials]:
        """Most recent fiscal years, newest first."""
        ...
