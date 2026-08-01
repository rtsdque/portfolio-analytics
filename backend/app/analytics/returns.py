"""Portfolio valuation and return calculations.

All functions take explicit price/holding data and return plain pandas objects.
No network access, no global state — everything here is unit-testable offline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def portfolio_value_series(
    prices: pd.DataFrame,
    shares: dict[str, float],
) -> pd.Series:
    """Dollar value of the portfolio on each date.

    Each holding contributes ``shares * price``. Summing raw prices instead of
    share-weighted values is the single most common error in naive trackers: it
    silently turns the result into an equal-price-weighted index, so a 3-share
    position in a $2,000 stock swamps a 500-share position in a $10 stock.
    """
    missing = [t for t in shares if t not in prices.columns]
    if missing:
        raise KeyError(f"No price data for tickers: {sorted(missing)}")

    weighted = pd.DataFrame(
        {t: prices[t].astype(float) * float(qty) for t, qty in shares.items()},
        index=prices.index,
    )
    return weighted.sum(axis=1)


def daily_returns(values: pd.Series) -> pd.Series:
    """Simple period-over-period returns, with the leading NaN dropped."""
    return values.astype(float).pct_change().dropna()


def total_return(values: pd.Series) -> float:
    """Fractional change from first to last observation (0.22 == +22%)."""
    first, last = float(values.iloc[0]), float(values.iloc[-1])
    if first == 0:
        raise ValueError("Cannot compute return from a zero starting value")
    return last / first - 1.0


def cagr(values: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    """Compound annual growth rate implied by the value series.

    Annualized over ELAPSED CALENDAR TIME when the index carries dates, falling
    back to a trading-day count otherwise.

    The distinction is not cosmetic. Counting periods and dividing by 252
    assumes exactly 252 trading days per year and that the window aligns to year
    boundaries; neither holds. On a real two-year window this measured 500/252 =
    1.9841 years against 1.9959 actual, understating elapsed time and so
    overstating CAGR by 0.13 percentage points. "Annual" means a calendar year —
    the denominator has to be calendar time.

    Volatility and Sharpe still scale by sqrt(252): those annualize a
    per-period statistic, which is a different operation from compounding a
    total return over elapsed time.
    """
    if len(values) < 2:
        raise ValueError("Need at least two observations to annualize")

    if isinstance(values.index, pd.DatetimeIndex):
        days = (values.index[-1] - values.index[0]).days
        years = days / 365.25
    else:
        years = (len(values) - 1) / periods_per_year

    if years <= 0:
        raise ValueError("Series spans no time; cannot annualize")

    return (1.0 + total_return(values)) ** (1.0 / years) - 1.0


def growth_of(values: pd.Series, base: float = 100.0) -> pd.Series:
    """Rebase a series so it starts at ``base`` — for comparing against a benchmark."""
    first = float(values.iloc[0])
    if first == 0:
        raise ValueError("Cannot rebase a series starting at zero")
    return values.astype(float) / first * base


def holding_breakdown(
    prices: pd.DataFrame,
    shares: dict[str, float],
    cost_basis: dict[str, float],
) -> pd.DataFrame:
    """Per-position cost, market value, and unrealized gain.

    ``cost_basis`` is the purchase price *per share*, matching how a brokerage
    statement reports average cost.
    """
    rows = []
    for ticker, qty in shares.items():
        if ticker not in prices.columns:
            raise KeyError(f"No price data for ticker: {ticker}")
        if ticker not in cost_basis:
            raise KeyError(f"No cost basis provided for ticker: {ticker}")

        price = float(prices[ticker].iloc[-1])
        cost = float(qty) * float(cost_basis[ticker])
        value = float(qty) * price
        rows.append(
            {
                "ticker": ticker,
                "shares": float(qty),
                "price": price,
                "cost_basis": cost,
                "market_value": value,
                "gain_loss": value - cost,
                "return_pct": (value / cost - 1.0) if cost else np.nan,
            }
        )

    frame = pd.DataFrame(rows).set_index("ticker")
    total_value = frame["market_value"].sum()
    frame["weight"] = frame["market_value"] / total_value if total_value else np.nan
    return frame.sort_values("market_value", ascending=False)


def contribution_to_return(
    prices: pd.DataFrame,
    shares: dict[str, float],
    cost_basis: dict[str, float],
) -> pd.Series:
    """How many percentage points of total portfolio return each holding supplied.

    Sums to the portfolio's overall return on cost, which makes it a genuine
    attribution rather than a list of individual position returns.
    """
    frame = holding_breakdown(prices, shares, cost_basis)
    total_cost = frame["cost_basis"].sum()
    if total_cost == 0:
        raise ValueError("Total cost basis is zero")
    return (frame["gain_loss"] / total_cost).sort_values(ascending=False)


def weights_from_holdings(
    prices: pd.DataFrame,
    shares: dict[str, float],
) -> pd.Series:
    """Current market-value weights, summing to 1.0."""
    latest = prices.iloc[-1]
    values = pd.Series(
        {t: float(latest[t]) * float(q) for t, q in shares.items()},
        dtype=float,
    )
    total = values.sum()
    if total == 0:
        raise ValueError("Portfolio has zero market value")
    return values / total
