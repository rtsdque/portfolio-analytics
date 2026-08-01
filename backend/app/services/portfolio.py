"""Assembles the Portfolio and Analytics page responses."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.analytics import concentration as C
from app.analytics import returns as R
from app.analytics import risk as K
from app.config import Settings
from app.providers.base import ProviderError
from app.schemas import (
    AnalyticsResponse,
    Caveat,
    ConcentrationSummary,
    CorrelationMatrix,
    DrawdownInfo,
    ExposureSlice,
    HoldingRow,
    PerformanceMetrics,
    PortfolioRequest,
    PortfolioResponse,
    PortfolioTotals,
    RiskContributionRow,
    Series,
    TimePoint,
)
from app.sectors import FUND, sector_for_sic
from app.services.filings import Filings
from app.services.market_data import MarketData

# Below this many observations, figures that project a return RATE onto a full
# year stop being informative.
#
# The line is drawn at projection, not at annualization generally. Volatility
# and Sharpe scale by sqrt(252) — noisy on a short window, but bounded and
# conventional. CAGR raises the total return to the power of 1/years, so as the
# window shrinks the exponent explodes: one good month reported +100.25% CAGR,
# which is arithmetically correct and completely useless. Alpha has the same
# problem, multiplying a noisy daily mean by 252.
#
# Those two are withheld rather than captioned. Everything the window actually
# realized — total return, drawdown, VaR, dispersion, dimensionless beta —
# still reports, because it describes what happened rather than extrapolating
# from it.
MIN_OBSERVATIONS = 60


class PortfolioService:
    def __init__(self, market: MarketData, filings: Filings, settings: Settings) -> None:
        self._market = market
        self._filings = filings
        self._settings = settings

    # ------------------------------------------------------------------ shared

    def _load(self, request: PortfolioRequest) -> tuple[pd.DataFrame, pd.Series | None, list[Caveat]]:
        caveats: list[Caveat] = []
        tickers = [h.ticker for h in request.holdings]
        end = date.today()
        start = end - timedelta(days=request.lookback_days)

        # Fetched separately and deliberately: a mistyped benchmark must not take
        # down a page whose holdings are all perfectly valid. Holdings failing is
        # a real error; the benchmark failing only costs the relative metrics.
        prices = self._market.daily_closes(tickers, start, end)
        if prices.empty:
            raise ProviderError("No price data returned for any requested symbol")

        benchmark = None
        try:
            bench_frame = self._market.daily_closes([request.benchmark], start, end)
            if request.benchmark in bench_frame.columns:
                benchmark = bench_frame[request.benchmark]
        except ProviderError:
            benchmark = None

        if benchmark is None:
            caveats.append(
                Caveat(
                    code="benchmark_unavailable",
                    level="warning",
                    message=(
                        f"No price data for benchmark {request.benchmark}. "
                        "Beta, alpha, tracking error, and information ratio are unavailable."
                    ),
                )
            )

        available = [t for t in tickers if t in prices.columns]
        holdings = prices[available].dropna(how="all")

        # Record where each ticker's own history begins before the join below
        # collapses the window to the common overlap.
        first_bars = {
            t: holdings[t].dropna().index[0]
            for t in available
            if holdings[t].notna().any()
        }

        holdings = holdings.ffill().dropna()

        if holdings.empty:
            raise ProviderError("No overlapping price history across the requested holdings")

        # dropna() clips every holding to the shortest series. That is correct —
        # a portfolio return needs a date where all positions have prices — but
        # it is silent, and a single recent listing can quietly turn a requested
        # five-year window into a few months. Say so.
        #
        # The comparison is against the EARLIEST data any holding had, not
        # against the resulting window start: after clipping, window_start
        # equals the late arrival's own first bar, so comparing to it would
        # never flag the very ticker that caused the truncation.
        window_start = holdings.index[0]
        if first_bars:
            earliest = min(first_bars.values())
            latest_ticker = max(first_bars, key=lambda t: first_bars[t])

            if window_start > earliest + pd.Timedelta(days=3):
                lost = (window_start - earliest).days
                caveats.append(
                    Caveat(
                        code="window_truncated",
                        level="warning",
                        message=(
                            f"Analysis window starts {window_start.date()}, {lost} days later "
                            f"than the available history, because {latest_ticker} has no prices "
                            f"before {first_bars[latest_ticker].date()}. Every metric covers only "
                            "the period all holdings share."
                        ),
                    )
                )

        if len(holdings) < MIN_OBSERVATIONS:
            caveats.append(
                Caveat(
                    code="short_history",
                    level="warning",
                    message=(
                        f"Only {len(holdings)} trading days of overlapping history. "
                        "Annualized growth and alpha are withheld — projecting a window "
                        "this short onto a full year produces figures that are "
                        "arithmetically correct and practically meaningless. Returns, "
                        "drawdown, and risk measures below describe the window itself "
                        "and are unaffected."
                    ),
                )
            )

        return holdings, benchmark, caveats

    def _sectors(self, tickers: list[str]) -> dict[str, str]:
        """SIC-derived sector per ticker; funds and non-filers fall back gracefully."""
        out: dict[str, str] = {}
        for ticker in tickers:
            try:
                profile = self._filings.profile(ticker)
                out[ticker] = sector_for_sic(profile.sic)
            except ProviderError:
                # ETFs and other non-filers simply have no SIC code to read.
                out[ticker] = FUND
        return out

    # --------------------------------------------------------------- portfolio

    def build_portfolio(self, request: PortfolioRequest) -> PortfolioResponse:
        holdings_prices, benchmark, caveats = self._load(request)

        shares = {h.ticker: h.shares for h in request.holdings if h.ticker in holdings_prices}
        values = R.portfolio_value_series(holdings_prices, shares)
        weights = R.weights_from_holdings(holdings_prices, shares)
        rets = R.daily_returns(values)

        cost_map = {
            h.ticker: h.cost_basis
            for h in request.holdings
            if h.cost_basis is not None and h.ticker in shares
        }
        have_all_costs = len(cost_map) == len(shares)
        if not have_all_costs:
            caveats.append(
                Caveat(
                    code="partial_cost_basis",
                    level="info",
                    message=(
                        "Cost basis missing for one or more holdings. Gain/loss and "
                        "return on cost are omitted where it is absent."
                    ),
                )
            )

        sectors = self._sectors(list(shares))
        names = self._names(list(shares))

        breakdown = (
            R.holding_breakdown(holdings_prices, shares, cost_map) if have_all_costs else None
        )
        contribution = (
            R.contribution_to_return(holdings_prices, shares, cost_map)
            if have_all_costs
            else None
        )

        latest = holdings_prices.iloc[-1]
        rows: list[HoldingRow] = []
        for ticker in sorted(shares, key=lambda t: -weights[t]):
            price = float(latest[ticker])
            qty = shares[ticker]
            row = HoldingRow(
                ticker=ticker,
                name=names.get(ticker),
                sector=sectors.get(ticker),
                shares=qty,
                price=price,
                market_value=qty * price,
                weight=float(weights[ticker]),
            )
            if breakdown is not None:
                detail = breakdown.loc[ticker]
                row.cost_basis = float(detail["cost_basis"])
                row.gain_loss = float(detail["gain_loss"])
                row.return_pct = float(detail["return_pct"])
                row.contribution_pct = float(contribution[ticker])
            rows.append(row)

        totals = PortfolioTotals(market_value=float(values.iloc[-1]))
        if breakdown is not None:
            totals.cost_basis = float(breakdown["cost_basis"].sum())
            totals.gain_loss = float(breakdown["gain_loss"].sum())
            totals.return_pct = totals.gain_loss / totals.cost_basis

        metrics = self._metrics(values, rets, benchmark)
        dd = K.max_drawdown(values)

        growth = [Series(label="Portfolio", points=_points(R.growth_of(values)))]
        if benchmark is not None:
            aligned = benchmark.reindex(values.index).ffill().dropna()
            if len(aligned) > 1:
                growth.append(
                    Series(label=request.benchmark, points=_points(R.growth_of(aligned)))
                )

        return PortfolioResponse(
            as_of=values.index[-1].date(),
            start_date=values.index[0].date(),
            benchmark=request.benchmark,
            holdings=rows,
            totals=totals,
            metrics=metrics,
            drawdown=DrawdownInfo(
                max_drawdown=dd.max_drawdown,
                peak_date=dd.peak_date.date(),
                trough_date=dd.trough_date.date(),
                recovery_date=dd.recovery_date.date() if dd.recovery_date else None,
                is_recovered=dd.is_recovered,
            ),
            value_series=Series(label="Value", points=_points(values)),
            growth_series=growth,
            drawdown_series=Series(label="Drawdown", points=_points(K.drawdown_series(values))),
            caveats=caveats,
        )

    def _metrics(
        self,
        values: pd.Series,
        rets: pd.Series,
        benchmark: pd.Series | None,
    ) -> PerformanceMetrics:
        rf = self._settings.risk_free_rate
        projectable = len(values) >= MIN_OBSERVATIONS

        metrics = PerformanceMetrics(
            total_return=R.total_return(values),
            cagr=R.cagr(values) if projectable else None,
            volatility=K.annualized_volatility(rets),
            sharpe=_finite(K.sharpe_ratio(rets, rf)),
            sortino=_finite(K.sortino_ratio(rets, rf)),
            var_95=K.value_at_risk(rets),
            cvar_95=K.conditional_value_at_risk(rets),
        )

        if benchmark is not None:
            bench_rets = R.daily_returns(benchmark.reindex(values.index).ffill().dropna())
            if len(bench_rets) > 1:
                metrics.beta = _finite(K.beta(rets, bench_rets))
                metrics.alpha = (
                    _finite(K.jensens_alpha(rets, bench_rets, rf)) if projectable else None
                )
                metrics.tracking_error = _finite(K.tracking_error(rets, bench_rets))
                metrics.information_ratio = _finite(K.information_ratio(rets, bench_rets))
                metrics.benchmark_return = R.total_return(benchmark.dropna())

        return metrics

    def _names(self, tickers: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for ticker in tickers:
            try:
                out[ticker] = self._filings.profile(ticker).name
            except ProviderError:
                continue
        return out

    # --------------------------------------------------------------- analytics

    def build_analytics(self, request: PortfolioRequest) -> AnalyticsResponse:
        holdings_prices, _, caveats = self._load(request)

        shares = {h.ticker: h.shares for h in request.holdings if h.ticker in holdings_prices}
        weights = R.weights_from_holdings(holdings_prices, shares)
        values = R.portfolio_value_series(holdings_prices, shares)

        holding_rets = holdings_prices.pct_change().dropna()
        cov = K.covariance_matrix(holding_rets)
        contrib = K.risk_contribution(weights, cov)

        report = C.report(weights)
        sectors = self._sectors(list(shares))
        exposure = C.group_exposure(weights, sectors)

        if FUND in exposure.index:
            caveats.append(
                Caveat(
                    code="fund_sector_unknown",
                    level="info",
                    message=(
                        "ETFs and funds have no SIC code, so their underlying sector "
                        "exposure is not resolved. They are grouped separately."
                    ),
                )
            )

        realized = K.annualized_volatility(R.daily_returns(values))
        model_vol = K.portfolio_volatility(weights, cov)
        caveats.append(
            Caveat(
                code="volatility_basis",
                level="info",
                message=(
                    f"Realized volatility ({realized:.1%}) reflects how weights actually "
                    f"drifted over the window. Model volatility ({model_vol:.1%}) applies "
                    "today's weights to the full-period covariance. They answer different "
                    "questions and are expected to differ."
                ),
            )
        )

        corr = K.correlation_matrix(holding_rets)

        return AnalyticsResponse(
            as_of=holdings_prices.index[-1].date(),
            concentration=ConcentrationSummary(
                hhi=report.hhi,
                effective_holdings=report.effective_holdings,
                n_holdings=report.n_holdings,
                top_ticker=report.top_ticker,
                top_weight=report.top_weight,
                top_5_weight=report.top_5_weight,
                label=report.label,
            ),
            risk_contribution=[
                RiskContributionRow(
                    ticker=str(ticker),
                    weight=float(row["weight"]),
                    pct_of_risk=float(row["pct_of_risk"]),
                    risk_premium=float(row["pct_of_risk"] - row["weight"]),
                )
                for ticker, row in contrib.iterrows()
            ],
            portfolio_volatility=model_vol,
            realized_volatility=realized,
            sector_exposure=[
                ExposureSlice(label=str(label), weight=float(weight))
                for label, weight in exposure.items()
            ],
            correlation=CorrelationMatrix(
                tickers=[str(t) for t in corr.columns],
                values=[[float(v) for v in row] for row in corr.to_numpy()],
            ),
            caveats=caveats,
        )


def _points(series: pd.Series) -> list[TimePoint]:
    return [
        TimePoint(date=idx.date(), value=float(value))
        for idx, value in series.items()
        if np.isfinite(value)
    ]


def _finite(value: float | None) -> float | None:
    """Convert NaN/inf to None so JSON stays valid and the UI can show a dash."""
    if value is None:
        return None
    return float(value) if np.isfinite(value) else None
