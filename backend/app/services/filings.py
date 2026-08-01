"""Cached access to SEC filing data."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime

from app import cache
from app.analytics.credit import Financials
from app.providers.base import AnnualFinancials, CompanyProfile
from app.providers.edgar import EdgarProvider


class Filings:
    def __init__(self, provider: EdgarProvider, session_factory) -> None:
        self._provider = provider
        self._session_factory = session_factory

    def profile(self, symbol: str) -> CompanyProfile:
        symbol = symbol.strip().upper()
        with self._session_factory() as session:
            cached = cache.load_filing(session, symbol, "profile")
            if cached is not None:
                return CompanyProfile(**cached)

            profile = self._provider.get_profile(symbol)
            cache.store_filing(session, symbol, "profile", asdict(profile))
            return profile

    def annual(self, symbol: str, years: int = 2) -> list[AnnualFinancials]:
        symbol = symbol.strip().upper()
        with self._session_factory() as session:
            cached = cache.load_filing(session, symbol, f"annual:{years}")
            if cached is not None:
                return [_decode(row) for row in cached]

            rows = self._provider.get_annual_financials(symbol, years=years)
            cache.store_filing(
                session, symbol, f"annual:{years}", [_encode(row) for row in rows]
            )
            return rows


def _encode(row: AnnualFinancials) -> dict:
    return {
        "fiscal_year": row.fiscal_year,
        "period_end": row.period_end.isoformat(),
        "form": row.form,
        "shares_source": row.shares_source,
        "financials": asdict(row.financials),
    }


def _decode(payload: dict) -> AnnualFinancials:
    return AnnualFinancials(
        fiscal_year=payload["fiscal_year"],
        period_end=_parse_date(payload["period_end"]),
        form=payload["form"],
        shares_source=payload.get("shares_source"),
        financials=Financials(**payload["financials"]),
    )


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()
