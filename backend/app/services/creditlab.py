"""Assembles the Credit Lab head-to-head comparison."""

from __future__ import annotations

from datetime import date, timedelta

from app.analytics import credit as CR
from app.analytics import returns as R
from app.analytics import risk as K
from app.config import Settings
from app.providers.base import ProviderError
from app.schemas import (
    Caveat,
    CompanyAssessment,
    CreditRequest,
    CreditResponse,
    FinancialsSummary,
    MertonDetail,
    PiotroskiDetail,
    ZScoreDetail,
)
from app.sectors import sector_for_sic
from app.services.filings import Filings
from app.services.market_data import MarketData

VOLATILITY_LOOKBACK_DAYS = 400

# When Altman says distress but Merton puts default probability this low, the
# two models are telling genuinely different stories and the user needs to know.
DISAGREEMENT_PD_CEILING = 0.05


class CreditLabService:
    def __init__(self, market: MarketData, filings: Filings, settings: Settings) -> None:
        self._market = market
        self._filings = filings
        self._settings = settings

    def compare(self, request: CreditRequest) -> CreditResponse:
        end = date.today()
        start = end - timedelta(days=VOLATILITY_LOOKBACK_DAYS)

        prices = self._market.daily_closes(request.symbols, start, end)
        companies = [self._assess(symbol, prices, end) for symbol in request.symbols]

        return CreditResponse(as_of=end, companies=companies, caveats=[])

    def _assess(self, symbol: str, prices, as_of: date) -> CompanyAssessment:
        caveats: list[Caveat] = []

        try:
            profile = self._filings.profile(symbol)
        except ProviderError as exc:
            return CompanyAssessment(
                symbol=symbol,
                name=symbol,
                sector="Unclassified",
                is_financial=False,
                caveats=[
                    Caveat(
                        code="not_a_filer",
                        level="blocking",
                        message=(
                            f"{symbol} has no SEC filings. ETFs, funds, and foreign "
                            f"issuers without US filings cannot be credit-scored. ({exc})"
                        ),
                    )
                ],
            )

        assessment = CompanyAssessment(
            symbol=symbol,
            name=profile.name,
            sic=profile.sic,
            sic_description=profile.sic_description,
            sector=sector_for_sic(profile.sic),
            is_financial=profile.is_financial,
        )

        price = None
        equity_vol = None
        if symbol in prices.columns:
            series = prices[symbol].dropna()
            if len(series) > 2:
                price = float(series.iloc[-1])
                equity_vol = K.annualized_volatility(R.daily_returns(series))
        assessment.price = price

        try:
            years = self._filings.annual(symbol, years=2)
        except ProviderError:
            # Reached by ETFs and trusts, which have a CIK and file with the SEC
            # but publish no XBRL financial statements. Say that plainly rather
            # than surfacing the upstream URL.
            caveats.append(
                Caveat(
                    code="no_financials",
                    level="blocking",
                    message=(
                        f"{symbol} files with the SEC but publishes no XBRL financial "
                        "statements. ETFs, trusts, and funds report differently from "
                        "operating companies and cannot be credit-scored."
                    ),
                )
            )
            assessment.caveats = caveats
            return assessment

        latest = years[0]
        fin = latest.financials
        assessment.financials = FinancialsSummary(
            fiscal_year=latest.fiscal_year,
            period_end=latest.period_end,
            form=latest.form,
            total_assets=fin.total_assets,
            total_liabilities=fin.total_liabilities,
            revenue=fin.revenue,
            ebit=fin.ebit,
            net_income=fin.net_income,
            book_equity=fin.book_equity,
            working_capital=fin.working_capital,
            current_ratio=fin.current_ratio if fin.current_liabilities else None,
            shares_outstanding=fin.shares_outstanding,
            shares_source=latest.shares_source,
        )

        if fin.shares_outstanding and price:
            assessment.market_cap = fin.shares_outstanding * price
            if latest.shares_are_approximate:
                caveats.append(
                    Caveat(
                        code="shares_approximate",
                        level="info",
                        message=(
                            "Share count is the weighted-average EPS denominator, not a "
                            "year-end count — this filer stopped tagging a point-in-time "
                            "figure. Market cap is approximate."
                        ),
                    )
                )
        else:
            caveats.append(
                Caveat(
                    code="no_market_cap",
                    level="warning",
                    message="Could not determine market cap; Altman Z and Merton are unavailable.",
                )
            )

        # Piotroski needs no market data, so compute it regardless.
        piotroski = None
        if len(years) >= 2:
            f = CR.piotroski_f_score(fin, years[1].financials)
            piotroski = f
            assessment.piotroski = PiotroskiDetail(
                score=f.score,
                evaluable=f.evaluable,
                max_score=f.max_score,
                signals=f.signals,
                unavailable=sorted(f.unavailable),
            )
            if not f.is_complete:
                caveats.append(
                    Caveat(
                        code="piotroski_partial",
                        level="info",
                        message=(
                            f"{len(f.unavailable)} of {f.max_score} Piotroski signals could not "
                            f"be evaluated from this filer's tagged data: "
                            f"{', '.join(sorted(f.unavailable))}. Score is out of {f.evaluable}."
                        ),
                    )
                )
        else:
            caveats.append(
                Caveat(
                    code="single_year",
                    level="warning",
                    message="Only one fiscal year available; Piotroski needs two.",
                )
            )

        if profile.is_financial:
            caveats.append(
                Caveat(
                    code="financial_sector",
                    level="blocking",
                    message=(
                        "Altman's Z-Score does not apply to banks, insurers, or REITs. "
                        "Leverage is their business model and working capital has no "
                        "comparable meaning, so the ratios are not interpretable."
                    ),
                )
            )
            assessment.caveats = caveats
            return assessment

        z = None
        merton = None

        if assessment.market_cap and profile.z_variant:
            z = CR.altman_z_score(fin, assessment.market_cap, variant=profile.z_variant)
            assessment.z_score = ZScoreDetail(
                score=z.score,
                zone=z.zone,
                variant=z.variant,
                components=z.components,
                weighted=z.weighted,
            )

            if equity_vol:
                barrier = CR.debt_face_value(fin)
                m = CR.merton_distance_to_default(
                    market_cap=assessment.market_cap,
                    equity_volatility=equity_vol,
                    face_value_debt=barrier,
                    risk_free_rate=self._settings.risk_free_rate,
                )
                merton = m
                assessment.merton = MertonDetail(
                    distance_to_default=m.distance_to_default,
                    probability_of_default=m.probability_of_default,
                    asset_volatility=m.asset_volatility,
                    equity_volatility=equity_vol,
                    debt_barrier=m.debt_face_value,
                    horizon_years=m.horizon_years,
                )

        if z is not None:
            grade, score = CR.composite_grade(z, merton, piotroski)
            assessment.composite_grade = grade
            assessment.composite_score = score

            if (
                z.zone == "Distress"
                and merton is not None
                and merton.probability_of_default < DISAGREEMENT_PD_CEILING
            ):
                caveats.append(
                    Caveat(
                        code="model_disagreement",
                        level="warning",
                        message=(
                            f"Altman places this company in distress while Merton implies only a "
                            f"{merton.probability_of_default:.1%} one-year default probability. "
                            "This gap is typical of manufacturers running a captive finance arm, "
                            "whose lending book inflates balance-sheet leverage without the "
                            "operating distress Altman's ratios were fitted to detect. Read both."
                        ),
                    )
                )

        assessment.caveats = caveats
        return assessment
