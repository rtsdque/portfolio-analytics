"""API contract tests, driven by fake providers so CI needs no keys or network."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.analytics.credit import Financials
from app.cache import make_session_factory
from app.config import Settings
from app.deps import get_creditlab_service, get_portfolio_service
from app.main import app
from app.providers.base import AnnualFinancials, CompanyProfile, SymbolNotFound
from app.services.creditlab import CreditLabService
from app.services.filings import Filings
from app.services.market_data import MarketData
from app.services.portfolio import PortfolioService

PROFILES = {
    "AAPL": CompanyProfile("AAPL", "Apple Inc.", "0000320193", "3571", "Electronic Computers"),
    "KO": CompanyProfile("KO", "Coca Cola Co", "0000021344", "2080", "Beverages"),
    "JPM": CompanyProfile("JPM", "JPMorgan Chase", "0000019617", "6021", "National Commercial Banks"),
    "F": CompanyProfile("F", "Ford Motor Co", "0000037996", "3711", "Motor Vehicles"),
}


def _synthetic_prices(symbols, start, end, seed=3):
    """Deterministic random walks — enough structure for every metric to compute."""
    days = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    data = {}
    for i, symbol in enumerate(symbols):
        drift, vol = 0.0004 + i * 0.0001, 0.010 + i * 0.004
        steps = rng.normal(drift, vol, len(days))
        data[symbol] = 100.0 * np.exp(np.cumsum(steps))
    frame = pd.DataFrame(data, index=days)
    frame.index.name = "date"
    return frame


class FakePriceProvider:
    def __init__(self, known=("AAPL", "KO", "JPM", "F", "TSLA", "SPY"), late_listings=None):
        self.known = set(known)
        # ticker -> how many leading rows have no price, simulating a listing
        # that began partway through the requested window.
        self.late_listings = late_listings or {}

    def get_daily_closes(self, symbols, start, end):
        missing = [s for s in symbols if s not in self.known]
        if missing:
            raise SymbolNotFound(f"Alpaca returned no bars for: {sorted(missing)}")

        frame = _synthetic_prices(symbols, start, end)
        for ticker, blank_rows in self.late_listings.items():
            if ticker in frame.columns:
                frame.iloc[:blank_rows, frame.columns.get_loc(ticker)] = np.nan
        return frame

    def get_latest_prices(self, symbols):
        raise NotImplementedError


def _financials(scale=1.0, year=2024, healthy=True):
    # Share counts differ sharply between the two cases on purpose. X4
    # (market equity / total liabilities) dominates the Z-Score, so a distressed
    # balance sheet paired with a large market cap still scores Safe. Modelling
    # distress requires a small equity base, not just bad fundamentals.
    if healthy:
        return Financials(
            total_assets=1000 * scale,
            total_liabilities=400 * scale,
            current_assets=500 * scale,
            current_liabilities=200 * scale,
            retained_earnings=300 * scale,
            ebit=150 * scale,
            revenue=1200 * scale,
            net_income=100 * scale,
            book_equity=600 * scale,
            long_term_debt=200 * scale,
            cash_from_operations=140 * scale,
            gross_profit=480 * scale,
            shares_outstanding=100.0,
        )
    return Financials(
        total_assets=1000 * scale,
        total_liabilities=950 * scale,
        current_assets=150 * scale,
        current_liabilities=400 * scale,
        retained_earnings=-300 * scale,
        ebit=-80 * scale,
        revenue=400 * scale,
        net_income=-120 * scale,
        book_equity=50 * scale,
        long_term_debt=550 * scale,
        cash_from_operations=-40 * scale,
        gross_profit=60 * scale,
        shares_outstanding=1.0,
    )


class FakeEdgarProvider:
    def __init__(self, unhealthy=(), no_facts=()):
        self.unhealthy = set(unhealthy)
        self.no_facts = set(no_facts)

    def get_profile(self, symbol):
        if symbol not in PROFILES:
            raise SymbolNotFound(f"No SEC filer found for ticker {symbol!r}")
        return PROFILES[symbol]

    def get_annual_financials(self, symbol, years=2):
        if symbol in self.no_facts:
            raise SymbolNotFound(f"EDGAR has no data for {symbol}")
        healthy = symbol not in self.unhealthy
        return [
            AnnualFinancials(
                fiscal_year=2024 - i,
                period_end=date(2024 - i, 12, 31),
                financials=_financials(1.0 - 0.1 * i, healthy=healthy),
                form="10-K",
                shares_source="point_in_time",
            )
            for i in range(years)
        ]


@pytest.fixture
def client(tmp_path):
    settings = Settings(_env_file=None)
    factory = make_session_factory(f"sqlite:///{tmp_path / 'test-cache.db'}")

    market = MarketData(FakePriceProvider(), factory)
    filings = Filings(FakeEdgarProvider(unhealthy={"F"}, no_facts={"SPY"}), factory)

    app.dependency_overrides[get_portfolio_service] = lambda: PortfolioService(
        market, filings, settings
    )
    app.dependency_overrides[get_creditlab_service] = lambda: CreditLabService(
        market, filings, settings
    )

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


PORTFOLIO = {
    "holdings": [
        {"ticker": "AAPL", "shares": 40, "cost_basis": 90.0},
        {"ticker": "KO", "shares": 120, "cost_basis": 95.0},
        {"ticker": "JPM", "shares": 25, "cost_basis": 80.0},
    ],
    "benchmark": "SPY",
    "lookback_days": 730,
}


# ----------------------------------------------------------------------- basic


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_portfolio_shape(client):
    body = client.post("/api/portfolio", json=PORTFOLIO)
    assert body.status_code == 200
    data = body.json()

    assert len(data["holdings"]) == 3
    assert data["benchmark"] == "SPY"
    assert {s["label"] for s in data["growth_series"]} == {"Portfolio", "SPY"}
    assert len(data["value_series"]["points"]) > 100


def test_holdings_sorted_by_weight_and_sum_to_one(client):
    data = client.post("/api/portfolio", json=PORTFOLIO).json()
    weights = [h["weight"] for h in data["holdings"]]

    assert weights == sorted(weights, reverse=True)
    assert sum(weights) == pytest.approx(1.0)


def test_contribution_sums_to_total_return(client):
    """Attribution must reconcile, or the table is decorative."""
    data = client.post("/api/portfolio", json=PORTFOLIO).json()
    total = sum(h["contribution_pct"] for h in data["holdings"])

    assert total == pytest.approx(data["totals"]["return_pct"], rel=1e-9)


def test_market_value_reconciles_with_holdings(client):
    data = client.post("/api/portfolio", json=PORTFOLIO).json()
    summed = sum(h["market_value"] for h in data["holdings"])

    assert summed == pytest.approx(data["totals"]["market_value"])


def test_sectors_come_from_sic(client):
    data = client.post("/api/portfolio", json=PORTFOLIO).json()
    sectors = {h["ticker"]: h["sector"] for h in data["holdings"]}

    assert sectors["AAPL"] == "Technology Hardware"
    assert sectors["KO"] == "Food & Beverage"
    assert sectors["JPM"] == "Banking"


def test_growth_series_start_at_100(client):
    data = client.post("/api/portfolio", json=PORTFOLIO).json()
    for series in data["growth_series"]:
        assert series["points"][0]["value"] == pytest.approx(100.0)


# -------------------------------------------------------------------- caveats


def test_missing_cost_basis_omits_gain_and_flags_it(client):
    payload = {
        "holdings": [
            {"ticker": "AAPL", "shares": 40, "cost_basis": 90.0},
            {"ticker": "KO", "shares": 120},
        ],
        "benchmark": "SPY",
    }
    data = client.post("/api/portfolio", json=payload).json()

    assert data["totals"]["gain_loss"] is None
    assert all(h["return_pct"] is None for h in data["holdings"])
    assert "partial_cost_basis" in {c["code"] for c in data["caveats"]}


def test_unknown_benchmark_degrades_without_failing(client):
    payload = {**PORTFOLIO, "benchmark": "NOTREAL"}
    response = client.post("/api/portfolio", json=payload)

    # A bad benchmark must not take down the whole portfolio view.
    assert response.status_code == 200
    data = response.json()
    assert data["metrics"]["beta"] is None
    assert data["metrics"]["alpha"] is None
    assert "benchmark_unavailable" in {c["code"] for c in data["caveats"]}


def test_short_history_is_flagged(client):
    payload = {**PORTFOLIO, "lookback_days": 40}
    data = client.post("/api/portfolio", json=payload).json()

    assert "short_history" in {c["code"] for c in data["caveats"]}


def test_short_window_withholds_projected_figures(client):
    """A month annualized reported +100% CAGR. Withhold rather than caption."""
    data = client.post("/api/portfolio", json={**PORTFOLIO, "lookback_days": 40}).json()
    metrics = data["metrics"]

    assert metrics["cagr"] is None
    assert metrics["alpha"] is None


def test_short_window_still_reports_realized_figures(client):
    """Only projections are withheld — what the window did still reports."""
    data = client.post("/api/portfolio", json={**PORTFOLIO, "lookback_days": 40}).json()
    metrics = data["metrics"]

    assert metrics["total_return"] is not None
    assert metrics["volatility"] is not None
    assert metrics["var_95"] is not None
    assert metrics["cvar_95"] is not None
    # Beta is dimensionless — a covariance ratio, not a projection.
    assert metrics["beta"] is not None
    assert data["drawdown"]["max_drawdown"] is not None
    assert data["totals"]["market_value"] > 0


def test_long_window_reports_projected_figures(client):
    data = client.post("/api/portfolio", json={**PORTFOLIO, "lookback_days": 730}).json()

    assert data["metrics"]["cagr"] is not None
    assert data["metrics"]["alpha"] is not None
    assert "short_history" not in {c["code"] for c in data["caveats"]}


def test_recent_listing_truncates_window_and_says_so(tmp_path):
    """A holding with no early history silently clips every other holding.

    The clipping is correct — a portfolio return needs a date where all
    positions have prices — but a two-year request quietly becoming a few
    months, unannounced, is how a chart ends up lying about its own period.
    """
    settings = Settings(_env_file=None)
    factory = make_session_factory(f"sqlite:///{tmp_path / 'late.db'}")

    market = MarketData(FakePriceProvider(late_listings={"KO": 400}), factory)
    filings = Filings(FakeEdgarProvider(), factory)

    app.dependency_overrides[get_portfolio_service] = lambda: PortfolioService(
        market, filings, settings
    )
    try:
        with TestClient(app) as c:
            data = c.post("/api/portfolio", json=PORTFOLIO).json()
    finally:
        app.dependency_overrides.clear()

    codes = {c["code"] for c in data["caveats"]}
    assert "window_truncated" in codes

    message = next(c["message"] for c in data["caveats"] if c["code"] == "window_truncated")
    assert "KO" in message


def test_full_history_does_not_claim_truncation(client):
    data = client.post("/api/portfolio", json=PORTFOLIO).json()
    assert "window_truncated" not in {c["code"] for c in data["caveats"]}


# ------------------------------------------------------------------ analytics


def test_analytics_shape(client):
    response = client.post("/api/analytics", json=PORTFOLIO)
    assert response.status_code == 200
    data = response.json()

    assert data["concentration"]["n_holdings"] == 3
    assert len(data["risk_contribution"]) == 3
    assert len(data["correlation"]["tickers"]) == 3


def test_risk_contributions_sum_to_one(client):
    data = client.post("/api/analytics", json=PORTFOLIO).json()
    assert sum(r["pct_of_risk"] for r in data["risk_contribution"]) == pytest.approx(1.0)


def test_risk_premium_is_risk_minus_weight(client):
    data = client.post("/api/analytics", json=PORTFOLIO).json()
    for row in data["risk_contribution"]:
        assert row["risk_premium"] == pytest.approx(row["pct_of_risk"] - row["weight"])


def test_sector_exposure_sums_to_one(client):
    data = client.post("/api/analytics", json=PORTFOLIO).json()
    assert sum(s["weight"] for s in data["sector_exposure"]) == pytest.approx(1.0)


def test_correlation_diagonal_is_one(client):
    data = client.post("/api/analytics", json=PORTFOLIO).json()
    values = data["correlation"]["values"]
    for i in range(len(values)):
        assert values[i][i] == pytest.approx(1.0)


def test_volatility_basis_is_always_explained(client):
    """The two volatility figures differ by design; never ship them unexplained."""
    data = client.post("/api/analytics", json=PORTFOLIO).json()
    assert "volatility_basis" in {c["code"] for c in data["caveats"]}


# --------------------------------------------------------------------- credit


def test_credit_comparison(client):
    response = client.post("/api/credit", json={"symbols": ["AAPL", "F"]})
    assert response.status_code == 200
    data = response.json()

    assert [c["symbol"] for c in data["companies"]] == ["AAPL", "F"]

    healthy, distressed = data["companies"]
    assert healthy["z_score"]["zone"] == "Safe"
    assert distressed["z_score"]["zone"] == "Distress"
    assert healthy["composite_score"] > distressed["composite_score"]


def test_z_components_reconcile_to_score(client):
    data = client.post("/api/credit", json={"symbols": ["AAPL"]}).json()
    z = data["companies"][0]["z_score"]

    assert sum(z["weighted"].values()) == pytest.approx(z["score"])


def test_financial_sector_is_blocked_not_scored(client):
    """A Z-Score for a bank would be a confidently wrong number."""
    data = client.post("/api/credit", json={"symbols": ["JPM"]}).json()
    company = data["companies"][0]

    assert company["is_financial"]
    assert company["z_score"] is None
    assert company["composite_grade"] is None
    blocking = [c for c in company["caveats"] if c["level"] == "blocking"]
    assert any(c["code"] == "financial_sector" for c in blocking)


def test_piotroski_still_computed_for_financials(client):
    data = client.post("/api/credit", json={"symbols": ["JPM"]}).json()
    assert data["companies"][0]["piotroski"] is not None


def test_non_filer_reports_cleanly_without_leaking_urls(client):
    data = client.post("/api/credit", json={"symbols": ["SPY"]}).json()
    company = data["companies"][0]

    assert company["composite_grade"] is None
    messages = [c["message"] for c in company["caveats"]]
    assert any("cannot be credit-scored" in m for m in messages)
    assert not any("http" in m for m in messages)


# ------------------------------------------------------------------ validation


@pytest.mark.parametrize(
    "payload",
    [
        {"holdings": []},
        {"holdings": [{"ticker": "AAPL", "shares": 0}]},
        {"holdings": [{"ticker": "AAPL", "shares": -5}]},
        {"holdings": [{"ticker": "AAPL", "shares": 1}, {"ticker": "AAPL", "shares": 2}]},
        {"holdings": [{"ticker": "AAPL", "shares": 1}], "lookback_days": 5},
    ],
)
def test_invalid_portfolio_requests_rejected(client, payload):
    assert client.post("/api/portfolio", json=payload).status_code == 422


def test_self_comparison_rejected(client):
    assert client.post("/api/credit", json={"symbols": ["AAPL", "AAPL"]}).status_code == 422


def test_more_than_two_companies_rejected(client):
    response = client.post("/api/credit", json={"symbols": ["AAPL", "KO", "JPM"]})
    assert response.status_code == 422


def test_tickers_normalized_to_uppercase(client):
    payload = {"holdings": [{"ticker": " aapl ", "shares": 10, "cost_basis": 90.0}]}
    data = client.post("/api/portfolio", json=payload).json()

    assert data["holdings"][0]["ticker"] == "AAPL"


def test_unknown_ticker_returns_404(client):
    payload = {"holdings": [{"ticker": "NOTREAL", "shares": 10}]}
    response = client.post("/api/portfolio", json=payload)

    assert response.status_code == 404
    assert response.json()["code"] == "symbol_not_found"
