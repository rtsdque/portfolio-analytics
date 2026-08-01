"""Concentration and diversification measures.

Weights are market-value fractions summing to ~1.0 (see
``returns.weights_from_holdings``).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Herfindahl thresholds, adapted from the DOJ/FTC merger guidelines' market
# concentration bands. Useful as a familiar reference point, though a portfolio
# is not a market — treat these as descriptive labels, not verdicts.
HHI_DIVERSIFIED = 0.10
HHI_MODERATE = 0.18


@dataclass(frozen=True)
class ConcentrationReport:
    hhi: float
    effective_holdings: float
    n_holdings: int
    top_weight: float
    top_ticker: str
    top_5_weight: float
    label: str


def _validate(weights: pd.Series) -> pd.Series:
    if weights.empty:
        raise ValueError("Cannot measure concentration of an empty portfolio")
    if (weights < 0).any():
        raise ValueError("Short positions are not supported by these measures")
    total = float(weights.sum())
    if total <= 0:
        raise ValueError("Weights must sum to a positive value")
    return weights.astype(float) / total


def hhi(weights: pd.Series) -> float:
    """Herfindahl-Hirschman Index: sum of squared weights.

    Ranges from 1/n (perfectly equal-weighted) to 1.0 (a single position).
    """
    w = _validate(weights)
    return float((w**2).sum())


def effective_holdings(weights: pd.Series) -> float:
    """Reciprocal of HHI — the equal-weighted position count with equivalent concentration.

    A portfolio of 30 names where one is 60% of assets can have an effective
    count near 3, which communicates the real exposure far better than "30
    holdings" does.
    """
    return 1.0 / hhi(weights)


def top_n_weight(weights: pd.Series, n: int = 5) -> float:
    """Combined weight of the n largest positions."""
    if n <= 0:
        raise ValueError("n must be positive")
    w = _validate(weights)
    return float(w.nlargest(n).sum())


def classify(hhi_value: float) -> str:
    if hhi_value < HHI_DIVERSIFIED:
        return "Diversified"
    if hhi_value < HHI_MODERATE:
        return "Moderately concentrated"
    return "Highly concentrated"


def group_exposure(
    weights: pd.Series,
    groups: dict[str, str],
    unknown_label: str = "Unknown",
) -> pd.Series:
    """Aggregate weights by sector, industry, geography, or asset class."""
    w = _validate(weights)
    mapped = w.groupby(lambda t: groups.get(t, unknown_label)).sum()
    return mapped.sort_values(ascending=False)


def report(weights: pd.Series) -> ConcentrationReport:
    """Full concentration summary for a set of holdings."""
    w = _validate(weights)
    h = float((w**2).sum())
    top = w.idxmax()
    return ConcentrationReport(
        hhi=h,
        effective_holdings=1.0 / h,
        n_holdings=int(len(w)),
        top_weight=float(w.max()),
        top_ticker=str(top),
        top_5_weight=float(w.nlargest(5).sum()),
        label=classify(h),
    )


def look_through(
    weights: pd.Series,
    fund_holdings: dict[str, dict[str, float]],
) -> pd.Series:
    """Resolve fund positions into their underlying names.

    ``fund_holdings`` maps a fund ticker to ``{underlying: weight_within_fund}``.
    Tickers absent from the mapping are treated as direct holdings.

    Without this step, overlapping funds hide true single-name exposure: holding
    VOO, QQQ, and AAPL separately can mean far more Apple risk than the surface
    weights suggest.
    """
    w = _validate(weights)
    exposures: dict[str, float] = {}

    for ticker, weight in w.items():
        underlying = fund_holdings.get(str(ticker))
        if not underlying:
            exposures[str(ticker)] = exposures.get(str(ticker), 0.0) + float(weight)
            continue

        inner_total = sum(underlying.values())
        if inner_total <= 0:
            raise ValueError(f"Fund {ticker} has non-positive constituent weights")

        for name, inner_weight in underlying.items():
            share = float(weight) * float(inner_weight) / inner_total
            exposures[name] = exposures.get(name, 0.0) + share

    return pd.Series(exposures).sort_values(ascending=False)
