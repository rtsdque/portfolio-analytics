"""Corporate credit and bankruptcy risk models.

These are published, peer-reviewed scoring models rather than a trained
classifier. That is a deliberate choice: there is no freely available labeled
bankruptcy dataset that maps onto arbitrary live tickers, so a fitted model
would either be trained on a stale academic sample whose features do not match
what we can pull from filings, or be fit on too few default events to mean
anything. The models below need no training data, are citable, and can show
their work to the user.

References:
  * Altman, E. (1968) "Financial Ratios, Discriminant Analysis and the
    Prediction of Corporate Bankruptcy", Journal of Finance.
  * Altman, E. (1983, 2000) Z'- and Z''-Score revisions for private firms and
    non-manufacturers.
  * Merton, R. (1974) "On the Pricing of Corporate Debt".
  * Bharath, S. & Shumway, T. (2008) "Forecasting Default with the Merton
    Distance to Default Model", Review of Financial Studies — source of the
    naive estimator used here.
  * Piotroski, J. (2000) "Value Investing: The Use of Historical Financial
    Statement Information", Journal of Accounting Research.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from scipy.stats import norm

ZoneLabel = Literal["Safe", "Grey", "Distress"]
ZVariant = Literal["public_manufacturer", "private", "non_manufacturer"]

# Financial-sector balance sheets make Altman's ratios meaningless: leverage is
# the business model, working capital is not a comparable concept, and X5
# (sales/assets) has no sensible interpretation for a bank. Callers should
# surface this rather than silently reporting a number.
UNSUPPORTED_SECTORS = frozenset({"Financial Services", "Financials", "Banks", "Insurance"})


@dataclass(frozen=True)
class Financials:
    """Balance-sheet and income-statement inputs, in consistent currency units.

    Field names follow the concepts the SEC XBRL ``companyfacts`` API exposes,
    so the provider layer can populate this directly from filings.
    """

    total_assets: float
    total_liabilities: float
    current_assets: float
    current_liabilities: float
    retained_earnings: float
    ebit: float
    revenue: float
    net_income: float
    book_equity: float
    long_term_debt: float = 0.0
    cash_from_operations: float | None = None
    gross_profit: float | None = None
    shares_outstanding: float | None = None

    def __post_init__(self) -> None:
        if self.total_assets <= 0:
            raise ValueError("total_assets must be positive")
        if self.total_liabilities < 0:
            raise ValueError("total_liabilities cannot be negative")

    @property
    def working_capital(self) -> float:
        return self.current_assets - self.current_liabilities

    @property
    def current_ratio(self) -> float:
        if self.current_liabilities == 0:
            return math.inf
        return self.current_assets / self.current_liabilities

    @property
    def roa(self) -> float:
        return self.net_income / self.total_assets

    @property
    def asset_turnover(self) -> float:
        return self.revenue / self.total_assets

    @property
    def gross_margin(self) -> float | None:
        if self.gross_profit is None or self.revenue == 0:
            return None
        return self.gross_profit / self.revenue


@dataclass(frozen=True)
class ZScoreResult:
    score: float
    zone: ZoneLabel
    variant: ZVariant
    components: dict[str, float]
    weighted: dict[str, float]


@dataclass(frozen=True)
class MertonResult:
    distance_to_default: float
    probability_of_default: float
    asset_volatility: float
    equity_value: float
    debt_face_value: float
    horizon_years: float


@dataclass(frozen=True)
class PiotroskiResult:
    score: int
    signals: dict[str, bool]
    max_score: int
    unavailable: frozenset[str] = frozenset()

    @property
    def evaluable(self) -> int:
        """How many of the nine signals had the data needed to be judged.

        A signal that could not be evaluated is reported False, which makes a
        low score ambiguous on its own: Ford scores 2/9 partly because its share
        count is untaggable in XBRL, not because it diluted. Callers should show
        ``score``/``evaluable`` and disclose the gap rather than presenting a raw
        x/9 as if all nine fired.
        """
        return self.max_score - len(self.unavailable)

    @property
    def is_complete(self) -> bool:
        return not self.unavailable

    @property
    def label(self) -> str:
        if self.score >= 7:
            return "Strong"
        if self.score >= 4:
            return "Moderate"
        return "Weak"


_Z_COEFFICIENTS: dict[ZVariant, dict[str, float]] = {
    "public_manufacturer": {"X1": 1.2, "X2": 1.4, "X3": 3.3, "X4": 0.6, "X5": 1.0},
    "private": {"X1": 0.717, "X2": 0.847, "X3": 3.107, "X4": 0.420, "X5": 0.998},
    "non_manufacturer": {"X1": 6.56, "X2": 3.26, "X3": 6.72, "X4": 1.05},
}

_Z_THRESHOLDS: dict[ZVariant, tuple[float, float]] = {
    "public_manufacturer": (1.81, 2.99),
    "private": (1.23, 2.90),
    "non_manufacturer": (1.10, 2.60),
}


def altman_z_score(
    fin: Financials,
    market_cap: float | None = None,
    variant: ZVariant = "public_manufacturer",
) -> ZScoreResult:
    """Altman Z-Score with the published coefficients for the chosen variant.

    ``market_cap`` supplies X4's numerator for the public variant. The private
    and non-manufacturer variants use book equity instead and ignore it.

    The non-manufacturer variant drops X5 (sales/assets) entirely, because asset
    turnover varies so much across service and retail businesses that including
    it distorts cross-industry comparison.
    """
    if variant not in _Z_COEFFICIENTS:
        raise ValueError(f"Unknown Z-Score variant: {variant}")
    if fin.total_liabilities == 0:
        raise ValueError("Cannot compute X4 with zero total liabilities")

    if variant == "public_manufacturer":
        if market_cap is None:
            raise ValueError("market_cap is required for the public_manufacturer variant")
        if market_cap <= 0:
            raise ValueError("market_cap must be positive")
        equity_for_x4 = market_cap
    else:
        equity_for_x4 = fin.book_equity

    components = {
        "X1": fin.working_capital / fin.total_assets,
        "X2": fin.retained_earnings / fin.total_assets,
        "X3": fin.ebit / fin.total_assets,
        "X4": equity_for_x4 / fin.total_liabilities,
    }
    if variant != "non_manufacturer":
        components["X5"] = fin.revenue / fin.total_assets

    coeffs = _Z_COEFFICIENTS[variant]
    weighted = {k: coeffs[k] * v for k, v in components.items()}
    score = sum(weighted.values())

    distress, safe = _Z_THRESHOLDS[variant]
    if score > safe:
        zone: ZoneLabel = "Safe"
    elif score >= distress:
        zone = "Grey"
    else:
        zone = "Distress"

    return ZScoreResult(
        score=score,
        zone=zone,
        variant=variant,
        components=components,
        weighted=weighted,
    )


def debt_face_value(fin: Financials) -> float:
    """Merton's default barrier: current liabilities plus half of long-term debt.

    This is the standard KMV convention — short-term obligations come due within
    the horizon in full, while long-term debt only partially matures.
    """
    return fin.current_liabilities + 0.5 * fin.long_term_debt


def merton_distance_to_default(
    market_cap: float,
    equity_volatility: float,
    face_value_debt: float,
    expected_return: float | None = None,
    risk_free_rate: float = 0.045,
    horizon_years: float = 1.0,
) -> MertonResult:
    """Naive Merton distance-to-default and implied one-year default probability.

    Uses the Bharath-Shumway naive estimator, which approximates asset
    volatility from equity volatility instead of solving the full two-equation
    system iteratively. Their paper shows the naive version forecasts default at
    least as well as the iterated solution, so the added complexity buys nothing.

    ``equity_volatility`` is annualized (0.35 == 35%). ``expected_return``
    defaults to the risk-free rate; passing a trailing equity return is also
    common, but it makes the output noisy for volatile names.
    """
    if market_cap <= 0:
        raise ValueError("market_cap must be positive")
    if face_value_debt <= 0:
        raise ValueError("face_value_debt must be positive")
    if equity_volatility <= 0:
        raise ValueError("equity_volatility must be positive")
    if horizon_years <= 0:
        raise ValueError("horizon_years must be positive")

    e, f = market_cap, face_value_debt
    total = e + f

    # Bharath-Shumway naive asset volatility: equity vol scaled by the equity
    # share of firm value, plus an assumed debt volatility term.
    debt_vol = 0.05 + 0.25 * equity_volatility
    asset_vol = (e / total) * equity_volatility + (f / total) * debt_vol

    mu = risk_free_rate if expected_return is None else expected_return

    numerator = math.log(total / f) + (mu - 0.5 * asset_vol**2) * horizon_years
    dd = numerator / (asset_vol * math.sqrt(horizon_years))

    return MertonResult(
        distance_to_default=dd,
        probability_of_default=float(norm.cdf(-dd)),
        asset_volatility=asset_vol,
        equity_value=e,
        debt_face_value=f,
        horizon_years=horizon_years,
    )


def piotroski_f_score(
    current: Financials,
    prior: Financials,
) -> PiotroskiResult:
    """Piotroski F-Score: nine binary fundamental-health signals, 0-9.

    Signals whose inputs are missing score as False rather than raising, so a
    partial filing still produces a usable score. Which ones could not be judged
    is reported in ``unavailable`` — read that alongside the score, because a
    False from absent data means something very different from a real failure.
    """
    cfo = current.cash_from_operations
    cfo_positive = cfo is not None and cfo > 0
    accruals = cfo is not None and (cfo / current.total_assets) > current.roa

    cur_margin, prior_margin = current.gross_margin, prior.gross_margin
    have_margins = cur_margin is not None and prior_margin is not None
    margin_improved = have_margins and cur_margin > prior_margin

    have_shares = (
        current.shares_outstanding is not None and prior.shares_outstanding is not None
    )
    no_dilution = have_shares and current.shares_outstanding <= prior.shares_outstanding

    unavailable: set[str] = set()
    if cfo is None:
        unavailable.update({"positive_cfo", "quality_of_earnings"})
    if not have_margins:
        unavailable.add("improving_margin")
    if not have_shares:
        unavailable.add("no_dilution")

    signals = {
        "positive_roa": current.roa > 0,
        "positive_cfo": cfo_positive,
        "improving_roa": current.roa > prior.roa,
        "quality_of_earnings": accruals,
        "decreasing_leverage": (
            current.long_term_debt / current.total_assets
            < prior.long_term_debt / prior.total_assets
        ),
        "improving_liquidity": current.current_ratio > prior.current_ratio,
        "no_dilution": no_dilution,
        "improving_margin": margin_improved,
        "improving_turnover": current.asset_turnover > prior.asset_turnover,
    }

    return PiotroskiResult(
        score=sum(signals.values()),
        signals=signals,
        max_score=len(signals),
        unavailable=frozenset(unavailable),
    )


def composite_grade(
    z: ZScoreResult,
    merton: MertonResult | None = None,
    piotroski: PiotroskiResult | None = None,
) -> tuple[str, float]:
    """Blend the models into a single 0-100 health score and letter grade.

    Weighting is 50% Z-Score zone, 30% Merton default probability, 20%
    Piotroski, renormalized over whichever models were supplied. The blend is
    a presentation convenience for the head-to-head view — the underlying
    component scores are what should be shown alongside it.
    """
    distress, safe = _Z_THRESHOLDS[z.variant]
    z_norm = max(0.0, min(1.0, (z.score - distress) / (safe - distress)))

    parts: list[tuple[float, float]] = [(0.50, z_norm)]

    if merton is not None:
        # A 10% one-year default probability maps to zero; 0% maps to one.
        parts.append((0.30, max(0.0, min(1.0, 1.0 - merton.probability_of_default / 0.10))))

    if piotroski is not None:
        parts.append((0.20, piotroski.score / piotroski.max_score))

    total_weight = sum(w for w, _ in parts)
    score = sum(w * v for w, v in parts) / total_weight * 100.0

    if score >= 85:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 55:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    return grade, score


def is_supported_sector(sector: str | None) -> bool:
    """Whether Altman's ratios are meaningful for this sector."""
    if sector is None:
        return True
    return sector not in UNSUPPORTED_SECTORS
