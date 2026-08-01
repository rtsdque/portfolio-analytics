import { PageHeader } from '../components/layout/AppShell'
import { HoldingsEditor } from '../components/HoldingsEditor'
import { MetricTile } from '../components/MetricTile'
import { ChartLegend, TimeSeriesChart } from '../components/charts/TimeSeriesChart'
import {
  Card,
  CardTitle,
  CaveatList,
  EmptyState,
  ErrorState,
  Spinner,
  Button,
} from '../components/ui/Primitives'
import { fetchPortfolio } from '../lib/api'
import {
  currency,
  direction,
  percent,
  ratio,
  shortDate,
} from '../lib/format'
import { useAsync } from '../lib/useAsync'
import { usePortfolio } from '../state/PortfolioContext'

export function PortfolioPage() {
  const portfolio = usePortfolio()
  const { holdings, benchmark, lookbackDays, isEmpty, loadSample } = portfolio

  const key = JSON.stringify({ holdings, benchmark, lookbackDays })
  const { data, error, loading, refetch } = useAsync(
    (options) => fetchPortfolio({ holdings, benchmark, lookbackDays }, options),
    [key],
    { enabled: !isEmpty },
  )

  return (
    <>
      <PageHeader
        eyebrow="Positions / Performance"
        title="Portfolio"
        subtitle="Share-weighted valuation, return attribution, and risk-adjusted performance against your benchmark."
      />

      <div className="grid gap-5 lg:grid-cols-[380px_1fr]">
        <HoldingsEditor />

        <div className="flex flex-col gap-5">
          {isEmpty && (
            <EmptyState
              title="Add a position to begin"
              body="Enter a ticker and share count on the left. Cost basis is optional — without it you still get valuation and risk, just not return on cost."
              action={<Button variant="primary" onClick={loadSample}>Load a sample portfolio</Button>}
            />
          )}

          {/* No skeleton flash on refetch: the previous render is held at
              reduced opacity so editing a holding does not collapse the layout
              and bounce it back. Only the very first load shows a spinner. */}
          {!isEmpty && loading && !data && (
            <Card>
              <Spinner label="Pulling prices and computing metrics…" />
            </Card>
          )}

          {!isEmpty && error && <ErrorState error={error} onRetry={refetch} />}

          {!isEmpty && data && (
            <div
              className={[
                'flex flex-col gap-5 transition-opacity duration-[--dur-base]',
                loading ? 'opacity-45' : 'opacity-100',
              ].join(' ')}
            >
              <Results data={data} benchmark={benchmark} />
            </div>
          )}
        </div>
      </div>
    </>
  )
}

function Results({ data, benchmark }) {
  const { totals, metrics, drawdown } = data
  const excess =
    metrics.benchmark_return != null ? metrics.total_return - metrics.benchmark_return : null

  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricTile
          label="Market value"
          value={currency(totals.market_value)}
          hint={`as of ${shortDate(data.as_of)}`}
          emphasis
        />
        <MetricTile
          label="Return on cost"
          value={percent(totals.return_pct, { sign: true })}
          delta={totals.return_pct}
          hint={totals.gain_loss != null ? currency(totals.gain_loss, { sign: true }) : undefined}
          emphasis
        />
        <MetricTile
          label={`vs ${benchmark}`}
          value={excess != null ? percent(excess, { sign: true }) : '—'}
          delta={excess}
          hint={
            metrics.benchmark_return != null
              ? `${benchmark} ${percent(metrics.benchmark_return, { sign: true })}`
              : 'benchmark unavailable'
          }
        />
        <MetricTile
          label="Max drawdown"
          value={percent(drawdown.max_drawdown)}
          hint={
            drawdown.is_recovered
              ? `recovered ${shortDate(drawdown.recovery_date)}`
              : 'not yet recovered'
          }
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricTile label="Total return" value={percent(metrics.total_return, { sign: true })} hint="over window" />
        <MetricTile label="Annualized (CAGR)" value={percent(metrics.cagr, { sign: true })} />
        <MetricTile label="Volatility" value={percent(metrics.volatility)} hint="annualized" />
        <MetricTile label="Sharpe" value={ratio(metrics.sharpe)} hint="risk-adjusted" />
        <MetricTile label="Sortino" value={ratio(metrics.sortino)} hint="downside only" />
        <MetricTile label="Beta" value={ratio(metrics.beta)} hint={`vs ${benchmark}`} />
        <MetricTile label="Alpha" value={percent(metrics.alpha, { sign: true })} hint="annualized" />
        <MetricTile label="VaR 95%" value={percent(metrics.var_95)} hint={`CVaR ${percent(metrics.cvar_95)}`} />
      </div>

      <GrowthCard data={data} benchmark={benchmark} />
      <DrawdownCard data={data} />

      <Card>
        <CardTitle hint="contribution sums to return on cost">Holdings</CardTitle>
        <div className="-mx-1 overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-line text-left text-[10.5px] uppercase tracking-[0.1em] text-ink-faint">
                <th className="px-1 pb-2 font-medium">Ticker</th>
                <th className="px-1 pb-2 font-medium">Sector</th>
                <th className="px-1 pb-2 text-right font-medium">Shares</th>
                <th className="px-1 pb-2 text-right font-medium">Price</th>
                <th className="px-1 pb-2 text-right font-medium">Value</th>
                <th className="px-1 pb-2 text-right font-medium">Weight</th>
                <th className="px-1 pb-2 text-right font-medium">Return</th>
                <th className="px-1 pb-2 text-right font-medium">Contribution</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-faint">
              {data.holdings.map((row) => {
                const dir = direction(row.return_pct)
                return (
                  <tr key={row.ticker} className="transition-colors duration-[--dur-quick] hover:bg-surface-1/60">
                    <td className="px-1 py-2.5">
                      <span className="font-medium text-ink">{row.ticker}</span>
                      {row.name && (
                        <span className="ml-2 text-[11.5px] text-ink-ghost">{row.name}</span>
                      )}
                    </td>
                    <td className="px-1 py-2.5 text-ink-faint">{row.sector ?? '—'}</td>
                    <td className="px-1 py-2.5 text-right text-ink-muted" data-numeric>
                      {row.shares}
                    </td>
                    <td className="px-1 py-2.5 text-right text-ink-muted" data-numeric>
                      {currency(row.price)}
                    </td>
                    <td className="px-1 py-2.5 text-right text-ink" data-numeric>
                      {currency(row.market_value)}
                    </td>
                    <td className="px-1 py-2.5 text-right text-ink-muted" data-numeric>
                      {percent(row.weight, { decimals: 1 })}
                    </td>
                    <td className={['px-1 py-2.5 text-right', dir.token].join(' ')} data-numeric>
                      {row.return_pct != null && <span aria-hidden="true">{dir.arrow} </span>}
                      {percent(row.return_pct, { sign: true, decimals: 1 })}
                    </td>
                    <td className="px-1 py-2.5 text-right text-ink-muted" data-numeric>
                      {percent(row.contribution_pct, { sign: true, decimals: 2 })}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <CaveatList caveats={data.caveats} />
    </>
  )
}

const SERIES_COLORS = ['var(--color-viz-1)', 'var(--color-viz-2)']

function GrowthCard({ data, benchmark }) {
  // Both series are indexed to 100 at the start of the window, which is what
  // lets them share one y-axis honestly. Plotting dollars against an index on
  // two scales would manufacture a correlation that isn't in the data.
  const series = data.growth_series.map((s, i) => ({
    label: s.label,
    points: s.points,
    color: SERIES_COLORS[i] ?? SERIES_COLORS[0],
    dashed: i > 0,
  }))

  return (
    <Card>
      <CardTitle hint={`indexed to 100 · ${shortDate(data.start_date)}`}>
        Growth vs {benchmark}
      </CardTitle>
      <ChartLegend series={series} />
      <TimeSeriesChart
        series={series}
        height={252}
        formatValue={(v) => ratio(v, { decimals: 1 })}
        formatTick={(v) => ratio(v, { decimals: 0 })}
        formatDate={shortDate}
      />
    </Card>
  )
}

function DrawdownCard({ data }) {
  const series = [
    {
      label: 'Drawdown',
      points: data.drawdown_series.points,
      color: 'var(--color-viz-loss)',
    },
  ]

  return (
    <Card>
      {/* Single series, so no legend box — the title already names what is
          plotted and a one-swatch legend would just restate it. */}
      <CardTitle hint={`worst ${percent(data.drawdown.max_drawdown)}`}>
        Drawdown from peak
      </CardTitle>
      <TimeSeriesChart
        series={series}
        height={190}
        fill
        zeroBaseline
        labelEnd={false}
        formatValue={(v) => percent(v, { decimals: 1 })}
        formatTick={(v) => percent(v, { decimals: 0 })}
        formatDate={shortDate}
      />
    </Card>
  )
}
