"""Risk and risk-adjusted performance metrics.

Conventions used throughout:
  * ``returns`` are simple (not log) periodic returns, typically daily.
  * ``rf_annual`` is a decimal annual risk-free rate (0.045 == 4.5%) and is
    converted to a periodic rate by simple division, the standard practice for
    daily Sharpe calculations.
  * Annualization uses sqrt(periods_per_year) for volatility.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252

# An annualized dispersion below this is floating-point noise, not signal.
#
# Exact `== 0` guards are not enough. A portfolio holding only SPY, measured
# against SPY, produces a tracking error of ~1.5e-15 rather than a clean zero —
# and dividing a noise numerator by a noise denominator yielded an information
# ratio of -0.81, which reads as real underperformance against an identical
# benchmark. Anything under this threshold is treated as undefined.
NEGLIGIBLE = 1e-9


@dataclass(frozen=True)
class DrawdownResult:
    max_drawdown: float
    peak_date: pd.Timestamp
    trough_date: pd.Timestamp
    recovery_date: pd.Timestamp | None

    @property
    def is_recovered(self) -> bool:
        return self.recovery_date is not None


def annualized_volatility(
    returns: pd.Series,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    """Annualized standard deviation of returns (sample stdev, ddof=1)."""
    if len(returns) < 2:
        raise ValueError("Need at least two returns to compute volatility")
    return float(returns.std(ddof=1) * np.sqrt(periods_per_year))


def sharpe_ratio(
    returns: pd.Series,
    rf_annual: float = 0.045,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    """Annualized Sharpe ratio: mean excess return over its own volatility."""
    if len(returns) < 2:
        raise ValueError("Need at least two returns to compute Sharpe")
    excess = returns - rf_annual / periods_per_year
    sd = excess.std(ddof=1)
    if not np.isfinite(sd) or sd * np.sqrt(periods_per_year) <= NEGLIGIBLE:
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(periods_per_year))


def sortino_ratio(
    returns: pd.Series,
    rf_annual: float = 0.045,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    """Annualized Sortino ratio — Sharpe, but penalizing only downside deviation.

    Upside volatility is not risk to an investor; Sharpe cannot tell the
    difference, which is why a portfolio with sharp gains can look 'riskier'
    than it is. Downside deviation is computed over the full sample (zeroing
    positive excess returns) rather than over only the negative subset, which
    is the convention that keeps it comparable to Sharpe.
    """
    if len(returns) < 2:
        raise ValueError("Need at least two returns to compute Sortino")
    excess = returns - rf_annual / periods_per_year
    downside = excess.where(excess < 0, 0.0)
    dd = np.sqrt((downside**2).mean())
    if not np.isfinite(dd) or dd * np.sqrt(periods_per_year) <= NEGLIGIBLE:
        return float("nan")
    return float(excess.mean() / dd * np.sqrt(periods_per_year))


def drawdown_series(values: pd.Series) -> pd.Series:
    """Fractional drawdown from the running peak at each point in time."""
    values = values.astype(float)
    return values / values.cummax() - 1.0


def max_drawdown(values: pd.Series) -> DrawdownResult:
    """Worst peak-to-trough decline, with the dates that bracket it."""
    if len(values) < 2:
        raise ValueError("Need at least two observations for drawdown")

    values = values.astype(float)
    dd = drawdown_series(values)
    trough = dd.idxmin()
    peak = values.loc[:trough].idxmax()

    after = values.loc[trough:]
    recovered = after[after >= values.loc[peak]]
    recovery = recovered.index[0] if len(recovered) else None

    return DrawdownResult(
        max_drawdown=float(dd.min()),
        peak_date=peak,
        trough_date=trough,
        recovery_date=recovery,
    )


def beta(returns: pd.Series, benchmark: pd.Series) -> float:
    """Sensitivity to the benchmark: cov(p, b) / var(b) over aligned dates."""
    p, b = returns.align(benchmark, join="inner")
    if len(p) < 2:
        raise ValueError("Need at least two overlapping returns to compute beta")
    var_b = b.var(ddof=1)
    if not np.isfinite(var_b) or np.sqrt(var_b * TRADING_DAYS) <= NEGLIGIBLE:
        return float("nan")
    return float(p.cov(b) / var_b)


def jensens_alpha(
    returns: pd.Series,
    benchmark: pd.Series,
    rf_annual: float = 0.045,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    """Annualized Jensen's alpha — return beyond what beta exposure explains."""
    p, b = returns.align(benchmark, join="inner")
    rf_period = rf_annual / periods_per_year
    b_val = beta(p, b)
    excess_p = (p - rf_period).mean()
    excess_b = (b - rf_period).mean()
    return float((excess_p - b_val * excess_b) * periods_per_year)


def tracking_error(
    returns: pd.Series,
    benchmark: pd.Series,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    """Annualized stdev of active return versus the benchmark."""
    p, b = returns.align(benchmark, join="inner")
    if len(p) < 2:
        raise ValueError("Need at least two overlapping returns")
    return float((p - b).std(ddof=1) * np.sqrt(periods_per_year))


def information_ratio(
    returns: pd.Series,
    benchmark: pd.Series,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    """Active return per unit of tracking error."""
    p, b = returns.align(benchmark, join="inner")
    te = tracking_error(p, b, periods_per_year)
    if not np.isfinite(te) or te <= NEGLIGIBLE:
        return float("nan")
    return float((p - b).mean() * periods_per_year / te)


def correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    """Pairwise Pearson correlation of holding returns."""
    return returns.corr()


def covariance_matrix(
    returns: pd.DataFrame,
    periods_per_year: int = TRADING_DAYS,
) -> pd.DataFrame:
    """Annualized covariance matrix of holding returns."""
    return returns.cov(ddof=1) * periods_per_year


def risk_contribution(
    weights: pd.Series,
    cov: pd.DataFrame,
) -> pd.DataFrame:
    """Decompose portfolio volatility into per-holding contributions.

    Returns marginal contribution to risk (MCR), component contribution (CCR,
    which sums exactly to portfolio volatility), and each holding's percentage
    share of total risk.

    This is the metric that most often surprises people: weight and risk share
    diverge sharply once correlations differ, so a 10% position in a volatile,
    uncorrelated name can contribute far more or far less than 10% of risk.
    """
    tickers = list(weights.index)
    cov = cov.loc[tickers, tickers]

    w = weights.to_numpy(dtype=float)
    sigma = cov.to_numpy(dtype=float)

    port_var = float(w @ sigma @ w)
    port_vol = np.sqrt(port_var)
    if port_vol == 0:
        raise ValueError("Portfolio volatility is zero; cannot attribute risk")

    mcr = (sigma @ w) / port_vol
    ccr = w * mcr

    return pd.DataFrame(
        {
            "weight": w,
            "mcr": mcr,
            "ccr": ccr,
            "pct_of_risk": ccr / port_vol,
        },
        index=tickers,
    ).sort_values("pct_of_risk", ascending=False)


def portfolio_volatility(weights: pd.Series, cov: pd.DataFrame) -> float:
    """Annualized portfolio volatility from weights and an annualized covariance matrix."""
    tickers = list(weights.index)
    w = weights.loc[tickers].to_numpy(dtype=float)
    sigma = cov.loc[tickers, tickers].to_numpy(dtype=float)
    return float(np.sqrt(w @ sigma @ w))


def value_at_risk(
    returns: pd.Series,
    confidence: float = 0.95,
) -> float:
    """Historical VaR — the loss threshold breached (1 - confidence) of the time.

    Returned as a negative number, e.g. -0.021 means "on the worst 5% of days,
    losses exceeded 2.1%".
    """
    if not 0 < confidence < 1:
        raise ValueError("confidence must be strictly between 0 and 1")
    if len(returns) < 2:
        raise ValueError("Need at least two returns for VaR")
    return float(np.quantile(returns.to_numpy(dtype=float), 1.0 - confidence))


def conditional_value_at_risk(
    returns: pd.Series,
    confidence: float = 0.95,
) -> float:
    """Expected shortfall — the average loss on days worse than VaR."""
    var = value_at_risk(returns, confidence)
    tail = returns[returns <= var]
    if tail.empty:
        return var
    return float(tail.mean())
