import pytest

from app.analytics import credit as CR


@pytest.fixture
def healthy():
    """A clean set of figures chosen so every Z-Score ratio is hand-checkable."""
    return CR.Financials(
        total_assets=1000.0,
        total_liabilities=400.0,
        current_assets=500.0,
        current_liabilities=200.0,
        retained_earnings=300.0,
        ebit=150.0,
        revenue=1200.0,
        net_income=100.0,
        book_equity=600.0,
        long_term_debt=200.0,
        cash_from_operations=140.0,
        gross_profit=480.0,
        shares_outstanding=100.0,
    )


@pytest.fixture
def distressed():
    return CR.Financials(
        total_assets=1000.0,
        total_liabilities=950.0,
        current_assets=150.0,
        current_liabilities=400.0,
        retained_earnings=-300.0,
        ebit=-80.0,
        revenue=400.0,
        net_income=-120.0,
        book_equity=50.0,
        long_term_debt=550.0,
        cash_from_operations=-40.0,
        gross_profit=60.0,
        shares_outstanding=140.0,
    )


def test_working_capital_and_ratios(healthy):
    assert healthy.working_capital == pytest.approx(300.0)
    assert healthy.current_ratio == pytest.approx(2.5)
    assert healthy.roa == pytest.approx(0.10)
    assert healthy.asset_turnover == pytest.approx(1.2)
    assert healthy.gross_margin == pytest.approx(0.40)


def test_financials_rejects_nonpositive_assets():
    with pytest.raises(ValueError, match="total_assets must be positive"):
        CR.Financials(
            total_assets=0.0,
            total_liabilities=10.0,
            current_assets=1.0,
            current_liabilities=1.0,
            retained_earnings=0.0,
            ebit=0.0,
            revenue=0.0,
            net_income=0.0,
            book_equity=0.0,
        )


def test_altman_z_public_matches_hand_calculation(healthy):
    result = CR.altman_z_score(healthy, market_cap=800.0)

    assert result.components["X1"] == pytest.approx(0.30)
    assert result.components["X2"] == pytest.approx(0.30)
    assert result.components["X3"] == pytest.approx(0.15)
    assert result.components["X4"] == pytest.approx(2.00)
    assert result.components["X5"] == pytest.approx(1.20)

    # 1.2(.30) + 1.4(.30) + 3.3(.15) + 0.6(2.0) + 1.0(1.2) = 3.675
    assert result.score == pytest.approx(3.675)
    assert result.zone == "Safe"


def test_weighted_components_sum_to_score(healthy):
    result = CR.altman_z_score(healthy, market_cap=800.0)
    assert sum(result.weighted.values()) == pytest.approx(result.score)


def test_altman_z_private_variant_uses_book_equity(healthy):
    result = CR.altman_z_score(healthy, variant="private")

    # X4 becomes book equity / total liabilities = 600/400 = 1.5
    assert result.components["X4"] == pytest.approx(1.5)
    assert result.score == pytest.approx(2.76285, rel=1e-5)
    assert result.zone == "Grey"


def test_altman_z_non_manufacturer_drops_x5(healthy):
    result = CR.altman_z_score(healthy, variant="non_manufacturer")

    assert "X5" not in result.components
    # 6.56(.30) + 3.26(.30) + 6.72(.15) + 1.05(1.5) = 5.529
    assert result.score == pytest.approx(5.529, rel=1e-6)
    assert result.zone == "Safe"


def test_distressed_company_lands_in_distress_zone(distressed):
    result = CR.altman_z_score(distressed, market_cap=60.0)

    assert result.score < 1.81
    assert result.zone == "Distress"


def test_public_variant_requires_market_cap(healthy):
    with pytest.raises(ValueError, match="market_cap is required"):
        CR.altman_z_score(healthy)


def test_unknown_variant_rejected(healthy):
    with pytest.raises(ValueError, match="Unknown Z-Score variant"):
        CR.altman_z_score(healthy, market_cap=800.0, variant="bogus")


def test_debt_face_value_uses_kmv_convention(healthy):
    # 200 current liabilities + half of 200 long-term debt
    assert CR.debt_face_value(healthy) == pytest.approx(300.0)


def test_merton_produces_sane_default_probability(healthy):
    result = CR.merton_distance_to_default(
        market_cap=800.0,
        equity_volatility=0.30,
        face_value_debt=CR.debt_face_value(healthy),
    )

    assert result.distance_to_default > 0
    assert 0.0 <= result.probability_of_default <= 1.0
    # A well-capitalized firm at 30% vol should be nowhere near default.
    assert result.probability_of_default < 0.01


def test_merton_pd_increases_with_volatility():
    low = CR.merton_distance_to_default(1000.0, 0.20, 500.0)
    high = CR.merton_distance_to_default(1000.0, 0.80, 500.0)

    assert high.probability_of_default > low.probability_of_default
    assert high.distance_to_default < low.distance_to_default


def test_merton_pd_increases_with_leverage():
    light = CR.merton_distance_to_default(1000.0, 0.40, 200.0)
    heavy = CR.merton_distance_to_default(1000.0, 0.40, 3000.0)

    assert heavy.probability_of_default > light.probability_of_default


def test_merton_asset_vol_below_equity_vol():
    """Leverage means asset volatility is always damped relative to equity."""
    result = CR.merton_distance_to_default(1000.0, 0.50, 500.0)
    assert result.asset_volatility < 0.50


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"market_cap": 0.0, "equity_volatility": 0.3, "face_value_debt": 100.0}, "market_cap"),
        ({"market_cap": 100.0, "equity_volatility": 0.0, "face_value_debt": 100.0}, "equity_volatility"),
        ({"market_cap": 100.0, "equity_volatility": 0.3, "face_value_debt": 0.0}, "face_value_debt"),
    ],
)
def test_merton_validates_inputs(kwargs, message):
    with pytest.raises(ValueError, match=message):
        CR.merton_distance_to_default(**kwargs)


def test_piotroski_scores_improving_company(healthy):
    prior = CR.Financials(
        total_assets=900.0,
        total_liabilities=450.0,
        current_assets=380.0,
        current_liabilities=200.0,
        retained_earnings=200.0,
        ebit=90.0,
        revenue=900.0,
        net_income=45.0,
        book_equity=450.0,
        long_term_debt=250.0,
        cash_from_operations=60.0,
        gross_profit=315.0,
        shares_outstanding=100.0,
    )

    result = CR.piotroski_f_score(healthy, prior)

    assert result.signals["positive_roa"]
    assert result.signals["positive_cfo"]
    assert result.signals["improving_roa"]
    assert result.signals["decreasing_leverage"]
    assert result.signals["improving_liquidity"]
    assert result.signals["no_dilution"]
    assert result.signals["improving_margin"]
    assert result.signals["improving_turnover"]
    assert result.score >= 8
    assert result.label == "Strong"


def test_piotroski_scores_deteriorating_company(healthy, distressed):
    result = CR.piotroski_f_score(distressed, healthy)

    assert not result.signals["positive_roa"]
    assert not result.signals["positive_cfo"]
    assert not result.signals["improving_roa"]
    assert not result.signals["no_dilution"]
    assert result.score <= 2
    assert result.label == "Weak"


def test_piotroski_handles_missing_optional_data(healthy):
    partial = CR.Financials(
        total_assets=1000.0,
        total_liabilities=400.0,
        current_assets=500.0,
        current_liabilities=200.0,
        retained_earnings=300.0,
        ebit=150.0,
        revenue=1200.0,
        net_income=100.0,
        book_equity=600.0,
        long_term_debt=200.0,
    )

    result = CR.piotroski_f_score(partial, healthy)

    # Cash-flow, margin, and dilution signals cannot fire without the data,
    # but the call must still succeed.
    assert not result.signals["positive_cfo"]
    assert not result.signals["improving_margin"]
    assert not result.signals["no_dilution"]
    assert result.max_score == 9

    # Crucially, those four are reported as unevaluable rather than failed.
    assert result.unavailable == {
        "positive_cfo",
        "quality_of_earnings",
        "improving_margin",
        "no_dilution",
    }
    assert result.evaluable == 5
    assert not result.is_complete


def test_piotroski_marks_complete_data_as_complete(healthy):
    prior = CR.Financials(
        total_assets=900.0,
        total_liabilities=450.0,
        current_assets=380.0,
        current_liabilities=200.0,
        retained_earnings=200.0,
        ebit=90.0,
        revenue=900.0,
        net_income=45.0,
        book_equity=450.0,
        long_term_debt=250.0,
        cash_from_operations=60.0,
        gross_profit=315.0,
        shares_outstanding=100.0,
    )

    result = CR.piotroski_f_score(healthy, prior)

    assert result.is_complete
    assert result.unavailable == frozenset()
    assert result.evaluable == 9


def test_missing_share_count_does_not_read_as_dilution(healthy):
    """Ford's share count is untaggable in XBRL; that must not look like dilution."""
    no_shares = CR.Financials(
        total_assets=healthy.total_assets,
        total_liabilities=healthy.total_liabilities,
        current_assets=healthy.current_assets,
        current_liabilities=healthy.current_liabilities,
        retained_earnings=healthy.retained_earnings,
        ebit=healthy.ebit,
        revenue=healthy.revenue,
        net_income=healthy.net_income,
        book_equity=healthy.book_equity,
        long_term_debt=healthy.long_term_debt,
        cash_from_operations=healthy.cash_from_operations,
        gross_profit=healthy.gross_profit,
        shares_outstanding=None,
    )

    result = CR.piotroski_f_score(no_shares, no_shares)

    assert not result.signals["no_dilution"]
    assert "no_dilution" in result.unavailable
    assert result.evaluable == 8


def test_composite_grade_rewards_healthy_company(healthy):
    z = CR.altman_z_score(healthy, market_cap=800.0)
    merton = CR.merton_distance_to_default(800.0, 0.30, CR.debt_face_value(healthy))

    grade, score = CR.composite_grade(z, merton)

    assert grade in {"A", "B"}
    assert score > 70


def test_composite_grade_penalizes_distressed_company(distressed):
    z = CR.altman_z_score(distressed, market_cap=60.0)
    merton = CR.merton_distance_to_default(60.0, 0.90, CR.debt_face_value(distressed))

    grade, score = CR.composite_grade(z, merton)

    assert grade in {"D", "F"}
    assert score < 40


def test_composite_grade_renormalizes_with_partial_models(healthy):
    z = CR.altman_z_score(healthy, market_cap=800.0)

    _, z_only = CR.composite_grade(z)

    # With only the Z-Score supplied, its weight must scale to the full 100.
    assert z_only == pytest.approx(100.0)


def test_composite_score_bounded(distressed, healthy):
    for fin, cap in ((distressed, 60.0), (healthy, 800.0)):
        z = CR.altman_z_score(fin, market_cap=cap)
        _, score = CR.composite_grade(z)
        assert 0.0 <= score <= 100.0


@pytest.mark.parametrize(
    "sector,supported",
    [("Technology", True), ("Banks", False), ("Financial Services", False), (None, True)],
)
def test_sector_support_flags_financials(sector, supported):
    assert CR.is_supported_sector(sector) is supported
