"""SEC EDGAR fundamentals provider.

EDGAR is the authoritative source: it is the filings themselves, free, keyless,
and complete back a decade or more. The cost is that XBRL tagging varies by
filer, so every concept needs a candidate list rather than a single tag, and
some concepts have to be derived when a filer omits them.

Etiquette the SEC actually enforces:
  * A ``User-Agent`` identifying the caller. Requests without one get a 403.
  * No more than 10 requests/second.
"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime
from typing import Any, Iterable

import httpx

from app.analytics.credit import Financials
from app.config import Settings, get_settings
from app.providers.base import (
    AnnualFinancials,
    CompanyProfile,
    InsufficientData,
    ProviderError,
    RateLimited,
    SymbolNotFound,
)

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

# Balance-sheet concepts are instantaneous (a single "end" date); income and
# cash-flow concepts cover a period ("start" to "end").
_INSTANT_CONCEPTS: dict[str, tuple[str, ...]] = {
    "total_assets": ("Assets",),
    "total_liabilities": ("Liabilities",),
    "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "retained_earnings": ("RetainedEarningsAccumulatedDeficit",),
    "book_equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "long_term_debt": (
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "LongTermDebtAndCapitalLeaseObligations",
    ),
}

_PERIOD_CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "ebit": ("OperatingIncomeLoss",),
    "gross_profit": ("GrossProfit",),
    "cash_from_operations": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "pretax_income": (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ),
    "interest_expense": ("InterestExpense", "InterestExpenseDebt"),
}

_ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "20-F", "40-F"})


class _RateLimiter:
    """Simple wall-clock spacer to stay under the SEC's 10 req/s ceiling."""

    def __init__(self, min_interval: float = 0.15) -> None:
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last = time.monotonic()


class EdgarProvider:
    """Fundamentals from SEC XBRL company facts."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client or httpx.Client(
            headers=self._settings.sec_headers,
            timeout=self._settings.request_timeout,
            follow_redirects=True,
        )
        self._limiter = _RateLimiter()
        self._ticker_map: dict[str, str] | None = None

    # ---------------------------------------------------------------- requests

    def _get(self, url: str) -> Any:
        self._limiter.wait()
        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:
            raise ProviderError(f"EDGAR request failed: {exc}") from exc

        if response.status_code == 403:
            raise ProviderError(
                "EDGAR rejected the request (403). Set SEC_USER_AGENT in .env to "
                "'Your Name your.email@example.com' — the SEC requires a contact address."
            )
        if response.status_code == 429:
            raise RateLimited("EDGAR rate limit hit; back off and retry")
        if response.status_code == 404:
            raise SymbolNotFound(f"EDGAR has no data at {url}")
        if response.status_code >= 400:
            raise ProviderError(f"EDGAR returned {response.status_code} for {url}")

        return response.json()

    # ------------------------------------------------------------------ lookup

    def _load_ticker_map(self) -> dict[str, str]:
        if self._ticker_map is not None:
            return self._ticker_map

        payload = self._get(self._settings.sec_tickers_url)
        mapping: dict[str, str] = {}
        for entry in payload.values():
            ticker = str(entry.get("ticker", "")).upper()
            cik = entry.get("cik_str")
            if ticker and cik is not None:
                mapping[ticker] = f"{int(cik):010d}"

        if not mapping:
            raise ProviderError("SEC ticker map came back empty")

        self._ticker_map = mapping
        return mapping

    def resolve_cik(self, symbol: str) -> str:
        """Zero-padded 10-digit CIK for a ticker.

        Share-class separators differ between vendors: the SEC writes Berkshire
        class B as ``BRK-B`` while Alpaca (and most quote screens) write
        ``BRK.B``. Without normalising, every dual-class company failed lookup
        and was reported as "not an SEC filer" — which is simply untrue of
        Berkshire, Brown-Forman, and everything like them.
        """
        mapping = self._load_ticker_map()
        upper = symbol.strip().upper()

        for candidate in (upper, upper.replace(".", "-"), upper.replace("-", ".")):
            cik = mapping.get(candidate)
            if cik is not None:
                return cik

        raise SymbolNotFound(f"No SEC filer found for ticker {symbol!r}")

    # ----------------------------------------------------------------- profile

    def get_profile(self, symbol: str) -> CompanyProfile:
        cik = self.resolve_cik(symbol)
        payload = self._get(_SUBMISSIONS_URL.format(cik=cik))

        return CompanyProfile(
            symbol=symbol.upper(),
            name=str(payload.get("name", symbol.upper())),
            cik=cik,
            sic=str(payload["sic"]) if payload.get("sic") else None,
            sic_description=payload.get("sicDescription"),
        )

    # ------------------------------------------------------------- fundamentals

    def get_annual_financials(
        self,
        symbol: str,
        years: int = 2,
    ) -> list[AnnualFinancials]:
        if years < 1:
            raise ValueError("years must be at least 1")

        cik = self.resolve_cik(symbol)
        payload = self._get(f"{self._settings.sec_facts_url}/CIK{cik}.json")
        facts = payload.get("facts", {})
        if not facts:
            raise InsufficientData(f"No XBRL facts filed for {symbol!r}")

        instant = {
            field: _extract(facts, tags, instant=True)
            for field, tags in _INSTANT_CONCEPTS.items()
        }
        period = {
            field: _extract(facts, tags, instant=False)
            for field, tags in _PERIOD_CONCEPTS.items()
        }
        shares_instant, shares_weighted = _extract_shares(facts)

        # Only periods carrying both indispensable anchors are usable; the rest
        # of the concepts can be derived or defaulted. Keying on the period end
        # date is what keeps the balance sheet and income statement aligned.
        candidate_ends = sorted(
            set(instant["total_assets"]) & set(period["revenue"]),
            reverse=True,
        )
        if not candidate_ends:
            raise InsufficientData(
                f"{symbol!r} has no reporting period with both total assets and revenue"
            )

        results: list[AnnualFinancials] = []
        for end in candidate_ends:
            built = _build_financials(end, instant, period, shares_instant, shares_weighted)
            if built is None:
                continue
            fin, period_end, form, share_source = built
            results.append(
                AnnualFinancials(
                    fiscal_year=period_end.year,
                    period_end=period_end,
                    financials=fin,
                    form=form,
                    shares_source=share_source,
                )
            )
            if len(results) >= years:
                break

        if not results:
            raise InsufficientData(
                f"Could not assemble a complete statement set for {symbol!r}"
            )
        return results

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> EdgarProvider:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# ------------------------------------------------------------------- extraction


def _extract(
    facts: dict[str, Any],
    tags: Iterable[str],
    *,
    instant: bool,
    unit: str = "USD",
) -> dict[str, dict[str, Any]]:
    """Map period end date to the best annual fact among the candidate tags.

    Keyed on the ``end`` date rather than EDGAR's ``fy`` field. ``fy`` identifies
    the fiscal year of the *report* a fact appeared in, and a 10-K carries prior
    year comparatives, so one ``fy`` bucket can hold two different periods — mix
    concepts across it and you get a balance sheet from one year paired with an
    income statement from another.

    Candidate tags are tried in order, so a filer using a newer revenue concept
    wins over a legacy one; later tags only fill periods earlier ones missed.
    Within a single tag, the most recently filed value wins, which picks up
    restatements.
    """
    out: dict[str, dict[str, Any]] = {}

    for namespace in ("us-gaap", "ifrs-full"):
        namespace_facts = facts.get(namespace, {})
        for tag in tags:
            entries = namespace_facts.get(tag, {}).get("units", {}).get(unit)
            if not entries:
                continue

            per_tag: dict[str, dict[str, Any]] = {}
            for entry in entries:
                record = _parse_entry(entry, instant=instant)
                if record is None:
                    continue
                end = record["end"]
                existing = per_tag.get(end)
                if existing is None or record["filed"] >= existing["filed"]:
                    per_tag[end] = record

            for end, record in per_tag.items():
                out.setdefault(end, record)

    return out


def _parse_entry(entry: dict[str, Any], *, instant: bool) -> dict[str, Any] | None:
    if entry.get("form") not in _ANNUAL_FORMS:
        return None
    if entry.get("fp") != "FY":
        return None

    end = entry.get("end")
    val = entry.get("val")
    if end is None or val is None:
        return None

    start = entry.get("start")
    if instant:
        if start is not None:
            return None
    else:
        if start is None:
            return None
        span = (_parse_date(end) - _parse_date(start)).days
        # Annual figures only — this filters the quarterly and half-year facts
        # that also appear in a 10-K's tagged data.
        if not 330 <= span <= 400:
            return None

    return {
        "val": float(val),
        "end": end,
        "form": entry["form"],
        "filed": entry.get("filed", ""),
    }


def _extract_shares(
    facts: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Share counts, which need looser handling than the statement concepts.

    Returns ``(point_in_time, weighted_average)``.

    Point-in-time counts are the better input for market cap but are not
    reliably filed: Ford's last ``dei:EntityCommonStockSharesOutstanding`` is
    dated 2011. Weighted-average share counts, by contrast, are tagged by every
    filer every year because EPS cannot be reported without them — and they are
    what Piotroski's original dilution test actually used.
    """
    instant: dict[str, dict[str, Any]] = {}

    dei_entries = (
        facts.get("dei", {})
        .get("EntityCommonStockSharesOutstanding", {})
        .get("units", {})
        .get("shares", [])
    )
    for entry in dei_entries:
        end, val = entry.get("end"), entry.get("val")
        if end is None or val is None:
            continue
        existing = instant.get(end)
        filed = entry.get("filed", "")
        if existing is None or filed >= existing["filed"]:
            instant[end] = {
                "val": float(val),
                "end": end,
                "filed": filed,
                "form": entry.get("form", ""),
            }

    # Deliberately NOT falling back to CommonStockSharesIssued: issued includes
    # treasury stock and is a different concept. Coca-Cola reports ~7.0B issued
    # against ~4.3B outstanding, so substituting it silently overstates the count
    # by 60%. No value beats a wrong value.
    for end, record in _extract(
        facts, ("CommonStockSharesOutstanding",), instant=True, unit="shares"
    ).items():
        instant.setdefault(end, record)

    weighted = _extract(
        facts,
        (
            "WeightedAverageNumberOfDilutedSharesOutstanding",
            "WeightedAverageNumberOfSharesOutstandingBasic",
            "WeightedAverageNumberOfSharesOutstandingDiluted",
        ),
        instant=False,
        unit="shares",
    )

    return instant, weighted


def _resolve_shares(
    instant: dict[str, dict[str, Any]],
    weighted: dict[str, dict[str, Any]],
    period_end: str,
) -> tuple[float | None, str | None]:
    """Best available share count for a period, plus which source supplied it.

    Point-in-time wins when present; weighted average is the fallback. The
    source is reported so the UI can disclose that a market cap was built on an
    annual average rather than a year-end count.
    """
    target = _parse_date(period_end)

    # Cover-page counts are dated a few weeks after year end, so allow a window
    # wide enough to catch the filing without straying into the next year.
    best: tuple[int, float] | None = None
    for end, record in instant.items():
        delta = (_parse_date(end) - target).days
        if not -30 <= delta <= 120:
            continue
        if best is None or abs(delta) < best[0]:
            best = (abs(delta), float(record["val"]))
    if best is not None:
        return best[1], "point_in_time"

    record = weighted.get(period_end)
    if record is not None:
        return float(record["val"]), "weighted_average"

    return None, None


def _value(store: dict[str, dict[str, Any]], end: str) -> float | None:
    record = store.get(end)
    return None if record is None else float(record["val"])


def _build_financials(
    end: str,
    instant: dict[str, dict[str, dict[str, Any]]],
    period: dict[str, dict[str, dict[str, Any]]],
    shares_instant: dict[str, dict[str, Any]],
    shares_weighted: dict[str, dict[str, Any]],
) -> tuple[Financials, date, str, str | None] | None:
    total_assets = _value(instant["total_assets"], end)
    revenue = _value(period["revenue"], end)
    if total_assets is None or total_assets <= 0 or revenue is None:
        return None

    share_count, share_source = _resolve_shares(shares_instant, shares_weighted, end)

    book_equity = _value(instant["book_equity"], end)
    total_liabilities = _value(instant["total_liabilities"], end)
    if total_liabilities is None:
        # Many filers tag equity but not total liabilities; the balance sheet
        # identity recovers it exactly.
        if book_equity is None:
            return None
        total_liabilities = total_assets - book_equity
    if book_equity is None:
        book_equity = total_assets - total_liabilities

    if total_liabilities < 0:
        return None

    ebit = _value(period["ebit"], end)
    if ebit is None:
        pretax = _value(period["pretax_income"], end)
        interest = _value(period["interest_expense"], end)
        if pretax is not None:
            ebit = pretax + (interest or 0.0)
    if ebit is None:
        ebit = _value(period["net_income"], end)
    if ebit is None:
        return None

    net_income = _value(period["net_income"], end)
    if net_income is None:
        return None

    # Current assets/liabilities are genuinely absent for some filers (notably
    # unclassified balance sheets). Falling back to totals keeps working capital
    # defined rather than dropping the whole period.
    current_assets = _value(instant["current_assets"], end)
    current_liabilities = _value(instant["current_liabilities"], end)
    if current_assets is None:
        current_assets = total_assets
    if current_liabilities is None:
        current_liabilities = total_liabilities

    fin = Financials(
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        current_assets=current_assets,
        current_liabilities=current_liabilities,
        retained_earnings=_value(instant["retained_earnings"], end) or 0.0,
        ebit=ebit,
        revenue=revenue,
        net_income=net_income,
        book_equity=book_equity,
        long_term_debt=_value(instant["long_term_debt"], end) or 0.0,
        cash_from_operations=_value(period["cash_from_operations"], end),
        gross_profit=_value(period["gross_profit"], end),
        shares_outstanding=share_count,
    )

    anchor = instant["total_assets"][end]
    return fin, _parse_date(anchor["end"]), str(anchor["form"]), share_source


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()
