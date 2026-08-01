import numpy as np
import pandas as pd
import pytest

from app.analytics import risk as K


def test_annualized_volatility_matches_manual():
    returns = pd.Series([0.02, 0.0, 0.02, 0.0])
    expected = returns.std(ddof=1) * np.sqrt(252)
    assert K.annualized_volatility(returns) == pytest.approx(expected)


def test_sharpe_is_zero_for_zero_mean_excess():
    returns = pd.Series([0.01, -0.01, 0.01, -0.01])
    assert K.sharpe_ratio(returns, rf_annual=0.0) == pytest.approx(0.0)


def test_sharpe_matches_hand_calculation():
    returns = pd.Series([0.02, 0.0, 0.02, 0.0])
    # mean 0.01, sample stdev 0.0115470, annualized by sqrt(252)
    assert K.sharpe_ratio(returns, rf_annual=0.0) == pytest.approx(13.7477, rel=1e-3)


def test_sharpe_nan_when_volatility_is_zero():
    returns = pd.Series([0.01, 0.01, 0.01])
    assert np.isnan(K.sharpe_ratio(returns, rf_annual=0.0))


def test_sortino_ignores_upside_volatility():
    """A series whose volatility is almost entirely one big gain.

    Sharpe charges that spike as risk; Sortino should not, so Sortino must come
    out materially higher on the same data.
    """
    returns = pd.Series([0.10, -0.005, -0.005, -0.005, -0.005, -0.02])

    assert returns.mean() > 0
    sharpe = K.sharpe_ratio(returns, rf_annual=0.0)
    sortino = K.sortino_ratio(returns, rf_annual=0.0)

    assert sortino > sharpe * 2


def test_sortino_nan_without_downside():
    returns = pd.Series([0.01, 0.02, 0.03])
    assert np.isnan(K.sortino_ratio(returns, rf_annual=0.0))


def test_max_drawdown_finds_peak_and_trough():
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    values = pd.Series([100.0, 120.0, 90.0, 110.0, 130.0], index=idx)

    result = K.max_drawdown(values)

    assert result.max_drawdown == pytest.approx(-0.25)
    assert result.peak_date == idx[1]
    assert result.trough_date == idx[2]
    assert result.recovery_date == idx[4]
    assert result.is_recovered


def test_unrecovered_drawdown_has_no_recovery_date():
    values = pd.Series([100.0, 120.0, 90.0, 95.0])
    result = K.max_drawdown(values)

    assert result.recovery_date is None
    assert not result.is_recovered


def test_drawdown_series_is_never_positive():
    values = pd.Series([100.0, 120.0, 90.0, 110.0, 130.0])
    assert (K.drawdown_series(values) <= 1e-12).all()


def test_beta_of_leveraged_series():
    benchmark = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
    portfolio = benchmark * 2.0
    assert K.beta(portfolio, benchmark) == pytest.approx(2.0)


def test_beta_of_identical_series_is_one():
    benchmark = pd.Series([0.01, -0.02, 0.03, -0.01])
    assert K.beta(benchmark.copy(), benchmark) == pytest.approx(1.0)


def test_alpha_is_zero_when_portfolio_tracks_benchmark():
    benchmark = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
    assert K.jensens_alpha(benchmark.copy(), benchmark, rf_annual=0.0) == pytest.approx(
        0.0, abs=1e-12
    )


def test_alpha_positive_when_portfolio_adds_constant_excess():
    benchmark = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
    portfolio = benchmark + 0.001
    alpha = K.jensens_alpha(portfolio, benchmark, rf_annual=0.0)
    assert alpha == pytest.approx(0.001 * 252, rel=1e-9)


def test_tracking_error_zero_for_identical_series():
    benchmark = pd.Series([0.01, -0.02, 0.03])
    assert K.tracking_error(benchmark.copy(), benchmark) == pytest.approx(0.0)


def test_information_ratio_nan_without_tracking_error():
    benchmark = pd.Series([0.01, -0.02, 0.03])
    assert np.isnan(K.information_ratio(benchmark.copy(), benchmark))


def test_information_ratio_nan_when_tracking_error_is_float_noise():
    """A portfolio identical to its benchmark must not report an active return.

    Regression: holding only SPY against SPY produced a tracking error of
    ~1.5e-15 rather than exactly zero, so an `== 0` guard let it through and the
    ratio came out at -0.81 — noise over noise, presented as underperformance.
    """
    rng = np.random.default_rng(11)
    benchmark = pd.Series(rng.normal(0.0004, 0.011, 400))
    # Round-tripping through arithmetic reproduces the denormal residue that a
    # real pipeline produces when the same series is reconstructed.
    portfolio = (benchmark * 3.0) / 3.0

    te = K.tracking_error(portfolio, benchmark)
    assert te < 1e-9
    assert te >= 0

    assert np.isnan(K.information_ratio(portfolio, benchmark))


def test_beta_is_one_and_alpha_zero_against_self():
    rng = np.random.default_rng(12)
    benchmark = pd.Series(rng.normal(0.0004, 0.011, 400))
    portfolio = (benchmark * 3.0) / 3.0

    assert K.beta(portfolio, benchmark) == pytest.approx(1.0, abs=1e-9)
    assert K.jensens_alpha(portfolio, benchmark, rf_annual=0.0) == pytest.approx(0.0, abs=1e-9)


def test_sharpe_nan_for_negligible_dispersion():
    """Constant returns give a stdev of denormal noise, not a clean zero."""
    returns = pd.Series([0.01] * 200) * 3.0 / 3.0
    assert np.isnan(K.sharpe_ratio(returns, rf_annual=0.0))


def test_beta_aligns_on_shared_dates():
    idx_a = pd.date_range("2024-01-01", periods=5, freq="D")
    idx_b = pd.date_range("2024-01-03", periods=5, freq="D")
    portfolio = pd.Series([0.02, -0.04, 0.06, -0.02, 0.01], index=idx_a)
    benchmark = pd.Series([0.03, -0.01, 0.005, 0.01, -0.02], index=idx_b)

    # Only three dates overlap; the call must succeed rather than misalign.
    assert np.isfinite(K.beta(portfolio, benchmark))


def _sample_returns():
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {
            "AAPL": rng.normal(0.0005, 0.015, 300),
            "KO": rng.normal(0.0003, 0.008, 300),
            "NVDA": rng.normal(0.0010, 0.030, 300),
        }
    )


def test_risk_contribution_sums_to_portfolio_volatility():
    returns = _sample_returns()
    cov = K.covariance_matrix(returns)
    weights = pd.Series({"AAPL": 0.5, "KO": 0.3, "NVDA": 0.2})

    contrib = K.risk_contribution(weights, cov)
    port_vol = K.portfolio_volatility(weights, cov)

    assert contrib["ccr"].sum() == pytest.approx(port_vol)
    assert contrib["pct_of_risk"].sum() == pytest.approx(1.0)


def test_volatile_holding_contributes_more_risk_than_its_weight():
    returns = _sample_returns()
    cov = K.covariance_matrix(returns)
    weights = pd.Series({"AAPL": 0.4, "KO": 0.4, "NVDA": 0.2})

    contrib = K.risk_contribution(weights, cov)

    # NVDA is 20% of capital but roughly twice as volatile as AAPL and nearly
    # four times KO, so its share of risk must exceed its share of value.
    assert contrib.loc["NVDA", "pct_of_risk"] > contrib.loc["NVDA", "weight"]
    assert contrib.loc["KO", "pct_of_risk"] < contrib.loc["KO", "weight"]


def test_risk_contribution_rejects_zero_volatility():
    cov = pd.DataFrame(
        [[0.0, 0.0], [0.0, 0.0]], index=["A", "B"], columns=["A", "B"]
    )
    weights = pd.Series({"A": 0.5, "B": 0.5})

    with pytest.raises(ValueError, match="volatility is zero"):
        K.risk_contribution(weights, cov)


def test_correlation_matrix_diagonal_is_one():
    corr = K.correlation_matrix(_sample_returns())
    assert np.allclose(np.diag(corr.to_numpy()), 1.0)


def test_var_and_cvar_ordering():
    returns = pd.Series(_sample_returns()["NVDA"])
    var = K.value_at_risk(returns, 0.95)
    cvar = K.conditional_value_at_risk(returns, 0.95)

    # Expected shortfall is always at least as severe as VaR itself.
    assert cvar <= var < 0


def test_var_rejects_invalid_confidence():
    returns = pd.Series([0.01, -0.01, 0.02])
    with pytest.raises(ValueError, match="strictly between"):
        K.value_at_risk(returns, 1.5)
