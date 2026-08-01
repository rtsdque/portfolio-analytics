"""API request and response models — the contract the frontend renders from.

Design rules that hold across every schema here:

  * Numbers are returned raw, never pre-formatted. Fractions stay fractions
    (0.2233, not "22.33%") and currency stays a float. Formatting is a
    presentation concern and baking it in makes the values unusable for charts.
  * Anything that can be unknown is Optional and defaults to None. There is no
    sentinel zero — a missing Sharpe and a Sharpe of 0.0 are different facts.
  * Every computed figure that rests on an approximation or an inapplicable
    model carries a caveat, surfaced in `caveats`. Silent degradation is the
    failure mode that makes a finance tool untrustworthy.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CaveatLevel = Literal["info", "warning", "blocking"]


class Caveat(BaseModel):
    """A disclosure attached to a result the user needs to read before trusting it."""

    code: str
    level: CaveatLevel
    message: str


# --------------------------------------------------------------------- requests


class Holding(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    shares: float = Field(gt=0)
    cost_basis: float | None = Field(default=None, gt=0, description="Purchase price per share")

    @field_validator("ticker")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return value.strip().upper()


class PortfolioRequest(BaseModel):
    holdings: list[Holding] = Field(min_length=1, max_length=100)
    benchmark: str = "SPY"
    lookback_days: int = Field(default=730, ge=30, le=3650)

    @field_validator("benchmark")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("holdings")
    @classmethod
    def _no_duplicates(cls, value: list[Holding]) -> list[Holding]:
        seen = {h.ticker for h in value}
        if len(seen) != len(value):
            raise ValueError("Duplicate tickers in holdings")
        return value


class CreditRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=2)

    @field_validator("symbols")
    @classmethod
    def _normalize(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip().upper() for v in value]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Cannot compare a company against itself")
        return cleaned


# ---------------------------------------------------------------------- shared


class TimePoint(BaseModel):
    date: date
    value: float


class Series(BaseModel):
    label: str
    points: list[TimePoint]


# ------------------------------------------------------------------- portfolio


class HoldingRow(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    shares: float
    price: float
    market_value: float
    weight: float
    cost_basis: float | None = None
    gain_loss: float | None = None
    return_pct: float | None = None
    contribution_pct: float | None = None


class PortfolioTotals(BaseModel):
    market_value: float
    cost_basis: float | None = None
    gain_loss: float | None = None
    return_pct: float | None = None


class PerformanceMetrics(BaseModel):
    """Return and risk figures for the portfolio over the requested window."""

    total_return: float
    # None on windows too short to project a return rate onto a year — see
    # MIN_OBSERVATIONS in services/portfolio.py. Alpha below is withheld on the
    # same basis.
    cagr: float | None = None
    volatility: float
    sharpe: float | None = None
    sortino: float | None = None
    var_95: float
    cvar_95: float

    # Benchmark-relative. None when the benchmark could not be fetched.
    beta: float | None = None
    alpha: float | None = None
    tracking_error: float | None = None
    information_ratio: float | None = None
    benchmark_return: float | None = None


class DrawdownInfo(BaseModel):
    max_drawdown: float
    peak_date: date
    trough_date: date
    recovery_date: date | None = None
    is_recovered: bool


class PortfolioResponse(BaseModel):
    as_of: date
    start_date: date
    benchmark: str

    holdings: list[HoldingRow]
    totals: PortfolioTotals
    metrics: PerformanceMetrics
    drawdown: DrawdownInfo

    value_series: Series
    growth_series: list[Series] = Field(
        description="Portfolio and benchmark rebased to 100 for comparison"
    )
    drawdown_series: Series

    caveats: list[Caveat] = Field(default_factory=list)


# ------------------------------------------------------------------- analytics


class ConcentrationSummary(BaseModel):
    hhi: float
    effective_holdings: float
    n_holdings: int
    top_ticker: str
    top_weight: float
    top_5_weight: float
    label: str


class RiskContributionRow(BaseModel):
    ticker: str
    weight: float
    pct_of_risk: float
    # Positive when a holding carries more risk than its weight implies.
    risk_premium: float


class ExposureSlice(BaseModel):
    label: str
    weight: float


class CorrelationMatrix(BaseModel):
    tickers: list[str]
    values: list[list[float]]


class AnalyticsResponse(BaseModel):
    as_of: date
    concentration: ConcentrationSummary
    risk_contribution: list[RiskContributionRow]
    portfolio_volatility: float
    realized_volatility: float
    sector_exposure: list[ExposureSlice]
    correlation: CorrelationMatrix
    caveats: list[Caveat] = Field(default_factory=list)


# ------------------------------------------------------------------ credit lab


class ZScoreDetail(BaseModel):
    score: float
    zone: Literal["Safe", "Grey", "Distress"]
    variant: str
    components: dict[str, float]
    weighted: dict[str, float]


class MertonDetail(BaseModel):
    distance_to_default: float
    probability_of_default: float
    asset_volatility: float
    equity_volatility: float
    debt_barrier: float
    horizon_years: float


class PiotroskiDetail(BaseModel):
    score: int
    evaluable: int
    max_score: int
    signals: dict[str, bool]
    unavailable: list[str]


class FinancialsSummary(BaseModel):
    fiscal_year: int
    period_end: date
    form: str
    total_assets: float
    total_liabilities: float
    revenue: float
    ebit: float
    net_income: float
    book_equity: float
    working_capital: float
    current_ratio: float | None = None
    shares_outstanding: float | None = None
    shares_source: str | None = None


class CompanyAssessment(BaseModel):
    symbol: str
    name: str
    sic: str | None = None
    sic_description: str | None = None
    sector: str
    is_financial: bool

    price: float | None = None
    market_cap: float | None = None

    financials: FinancialsSummary | None = None
    z_score: ZScoreDetail | None = None
    merton: MertonDetail | None = None
    piotroski: PiotroskiDetail | None = None

    composite_grade: str | None = None
    composite_score: float | None = None

    caveats: list[Caveat] = Field(default_factory=list)

    @property
    def is_scoreable(self) -> bool:
        return self.composite_grade is not None


class CreditResponse(BaseModel):
    as_of: date
    companies: list[CompanyAssessment]
    caveats: list[Caveat] = Field(default_factory=list)


# ----------------------------------------------------------------------- error


class ErrorResponse(BaseModel):
    code: str
    message: str
    detail: str | None = None
