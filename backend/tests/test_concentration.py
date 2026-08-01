import pandas as pd
import pytest

from app.analytics import concentration as C


def test_hhi_of_equal_weights_is_one_over_n():
    weights = pd.Series({"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25})
    assert C.hhi(weights) == pytest.approx(0.25)


def test_hhi_of_single_position_is_one():
    assert C.hhi(pd.Series({"A": 1.0})) == pytest.approx(1.0)


def test_hhi_normalizes_unnormalized_weights():
    """Raw dollar values should give the same answer as fractions."""
    dollars = pd.Series({"A": 2500.0, "B": 2500.0, "C": 2500.0, "D": 2500.0})
    assert C.hhi(dollars) == pytest.approx(0.25)


def test_effective_holdings_equals_count_when_equal_weighted():
    weights = pd.Series({"A": 0.2, "B": 0.2, "C": 0.2, "D": 0.2, "E": 0.2})
    assert C.effective_holdings(weights) == pytest.approx(5.0)


def test_effective_holdings_collapses_under_concentration():
    """Thirty names, but one is 60% of assets."""
    weights = pd.Series({"BIG": 0.60, **{f"S{i}": 0.40 / 29 for i in range(29)}})

    assert len(weights) == 30
    assert C.effective_holdings(weights) < 3.0


def test_top_n_weight():
    weights = pd.Series({"A": 0.5, "B": 0.3, "C": 0.15, "D": 0.05})
    assert C.top_n_weight(weights, 2) == pytest.approx(0.8)
    assert C.top_n_weight(weights, 10) == pytest.approx(1.0)


def test_top_n_rejects_nonpositive_n():
    with pytest.raises(ValueError, match="must be positive"):
        C.top_n_weight(pd.Series({"A": 1.0}), 0)


@pytest.mark.parametrize(
    "hhi_value,expected",
    [(0.05, "Diversified"), (0.15, "Moderately concentrated"), (0.40, "Highly concentrated")],
)
def test_classify(hhi_value, expected):
    assert C.classify(hhi_value) == expected


def test_report_summarizes_portfolio():
    weights = pd.Series({"AAPL": 0.5, "MSFT": 0.3, "KO": 0.15, "JPM": 0.05})
    rep = C.report(weights)

    assert rep.n_holdings == 4
    assert rep.top_ticker == "AAPL"
    assert rep.top_weight == pytest.approx(0.5)
    assert rep.top_5_weight == pytest.approx(1.0)
    assert rep.hhi == pytest.approx(0.25 + 0.09 + 0.0225 + 0.0025)
    assert rep.label == "Highly concentrated"


def test_empty_portfolio_raises():
    with pytest.raises(ValueError, match="empty portfolio"):
        C.report(pd.Series(dtype=float))


def test_negative_weights_rejected():
    with pytest.raises(ValueError, match="Short positions"):
        C.hhi(pd.Series({"A": 1.5, "B": -0.5}))


def test_group_exposure_aggregates_by_sector():
    weights = pd.Series({"AAPL": 0.4, "MSFT": 0.3, "JPM": 0.2, "KO": 0.1})
    sectors = {"AAPL": "Tech", "MSFT": "Tech", "JPM": "Financials", "KO": "Staples"}

    exposure = C.group_exposure(weights, sectors)

    assert exposure["Tech"] == pytest.approx(0.7)
    assert exposure["Financials"] == pytest.approx(0.2)
    assert exposure.index[0] == "Tech"


def test_group_exposure_labels_unmapped_tickers():
    weights = pd.Series({"AAPL": 0.5, "WEIRD": 0.5})
    exposure = C.group_exposure(weights, {"AAPL": "Tech"})

    assert exposure["Unknown"] == pytest.approx(0.5)


def test_look_through_resolves_fund_into_constituents():
    weights = pd.Series({"VOO": 0.5, "AAPL": 0.5})
    funds = {"VOO": {"AAPL": 0.3, "MSFT": 0.7}}

    exposure = C.look_through(weights, funds)

    # Direct 50% AAPL plus 30% of the 50% VOO sleeve.
    assert exposure["AAPL"] == pytest.approx(0.65)
    assert exposure["MSFT"] == pytest.approx(0.35)
    assert exposure.sum() == pytest.approx(1.0)


def test_look_through_reveals_hidden_concentration():
    """Surface weights look diversified; look-through shows they are not."""
    weights = pd.Series({"VOO": 0.34, "QQQ": 0.33, "AAPL": 0.33})
    funds = {
        "VOO": {"AAPL": 0.07, "MSFT": 0.07, "OTHER": 0.86},
        "QQQ": {"AAPL": 0.09, "MSFT": 0.08, "OTHER": 0.83},
    }

    surface = C.report(weights)
    resolved = C.look_through(weights, funds)

    assert surface.top_weight == pytest.approx(0.34)
    assert resolved["AAPL"] > surface.top_weight * 0.9
    assert resolved.sum() == pytest.approx(1.0)


def test_look_through_passes_through_unmapped_tickers():
    weights = pd.Series({"AAPL": 0.6, "MSFT": 0.4})
    exposure = C.look_through(weights, {})

    assert exposure["AAPL"] == pytest.approx(0.6)
    assert exposure["MSFT"] == pytest.approx(0.4)


def test_look_through_rejects_empty_fund_weights():
    with pytest.raises(ValueError, match="non-positive"):
        C.look_through(pd.Series({"BAD": 1.0}), {"BAD": {"X": 0.0}})
