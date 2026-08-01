import pandas as pd
import pytest

from app.analytics import returns as R


def test_portfolio_value_is_share_weighted(prices, shares):
    values = R.portfolio_value_series(prices, shares)

    # 500 * 10 + 1 * 2000 = 7000
    assert values.iloc[0] == pytest.approx(7000.0)
    # 500 * 13 + 1 * 2030 = 8530
    assert values.iloc[-1] == pytest.approx(8530.0)


def test_share_weighting_differs_from_summing_raw_prices(prices, shares):
    """Guards against the equal-price-weighting bug.

    Summing raw prices would make the series start at 2010 and be driven almost
    entirely by BRKA, even though AAPL is 71% of the portfolio's actual value.
    """
    weighted = R.portfolio_value_series(prices, shares)
    naive = prices.sum(axis=1)

    assert weighted.iloc[0] != pytest.approx(naive.iloc[0])

    weighted_return = weighted.iloc[-1] / weighted.iloc[0] - 1
    naive_return = naive.iloc[-1] / naive.iloc[0] - 1
    assert weighted_return > naive_return * 2


def test_missing_ticker_raises(prices):
    with pytest.raises(KeyError, match="NVDA"):
        R.portfolio_value_series(prices, {"NVDA": 10.0})


def test_total_return(prices, shares):
    values = R.portfolio_value_series(prices, shares)
    assert R.total_return(values) == pytest.approx(8530.0 / 7000.0 - 1.0)


def test_total_return_rejects_zero_start():
    with pytest.raises(ValueError, match="zero starting value"):
        R.total_return(pd.Series([0.0, 5.0]))


def test_cagr_annualizes_on_trading_days_without_dates():
    # No DatetimeIndex, so it falls back to counting periods.
    values = pd.Series([100.0] + [200.0] * 252)
    assert R.cagr(values) == pytest.approx(1.0, abs=1e-6)


def test_cagr_uses_calendar_time_when_dates_are_present():
    """A doubling over one calendar year is a 100% CAGR, whatever the day count.

    Only 24 observations here — a trading-day basis would read this as
    24/252 = 0.095 years and report an absurd annualized figure.
    """
    index = pd.date_range("2024-01-01", "2024-12-31", periods=24)
    values = pd.Series([100.0] * 23 + [200.0], index=index)

    assert R.cagr(values) == pytest.approx(1.0, rel=0.01)


def test_cagr_denominator_is_elapsed_calendar_time():
    """The contract: the denominator is real elapsed time, not a period count.

    Asserted as an identity rather than a direction — which of the two bases is
    larger depends on how many holidays fall in the window, so a direction test
    passes or fails on the fixture's calendar rather than on the behaviour.
    """
    index = pd.bdate_range("2024-08-01", periods=501)
    values = pd.Series(range(100, 601), index=index, dtype=float)

    elapsed_years = (index[-1] - index[0]).days / 365.25
    expected = (1 + R.total_return(values)) ** (1 / elapsed_years) - 1

    assert R.cagr(values) == pytest.approx(expected, rel=1e-12)

    # And it is genuinely a different number from the period-count basis.
    trading = (1 + R.total_return(values)) ** (1 / (500 / 252)) - 1
    assert R.cagr(values) != pytest.approx(trading, rel=1e-4)


def test_cagr_needs_two_points():
    with pytest.raises(ValueError, match="at least two"):
        R.cagr(pd.Series([100.0]))


def test_growth_of_rebases_to_100(prices, shares):
    values = R.portfolio_value_series(prices, shares)
    rebased = R.growth_of(values)

    assert rebased.iloc[0] == pytest.approx(100.0)
    assert rebased.iloc[-1] == pytest.approx(8530.0 / 7000.0 * 100.0)


def test_holding_breakdown(prices, shares, cost_basis):
    frame = R.holding_breakdown(prices, shares, cost_basis)

    aapl = frame.loc["AAPL"]
    assert aapl["cost_basis"] == pytest.approx(4500.0)
    assert aapl["market_value"] == pytest.approx(6500.0)
    assert aapl["gain_loss"] == pytest.approx(2000.0)
    assert aapl["return_pct"] == pytest.approx(2000.0 / 4500.0)

    # Sorted by market value, so the larger AAPL position leads.
    assert frame.index[0] == "AAPL"
    assert frame["weight"].sum() == pytest.approx(1.0)


def test_holding_breakdown_requires_cost_basis(prices, shares):
    with pytest.raises(KeyError, match="cost basis"):
        R.holding_breakdown(prices, shares, {"AAPL": 9.0})


def test_contribution_to_return_sums_to_portfolio_return(prices, shares, cost_basis):
    contrib = R.contribution_to_return(prices, shares, cost_basis)
    frame = R.holding_breakdown(prices, shares, cost_basis)

    portfolio_return = frame["market_value"].sum() / frame["cost_basis"].sum() - 1.0
    assert contrib.sum() == pytest.approx(portfolio_return)


def test_weights_from_holdings(prices, shares):
    weights = R.weights_from_holdings(prices, shares)

    assert weights.sum() == pytest.approx(1.0)
    assert weights["AAPL"] == pytest.approx(6500.0 / 8530.0)
    assert weights["BRKA"] == pytest.approx(2030.0 / 8530.0)
