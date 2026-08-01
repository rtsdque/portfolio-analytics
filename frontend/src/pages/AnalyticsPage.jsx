import { PageHeader } from '../components/layout/AppShell'
import { MetricTile } from '../components/MetricTile'
import { CorrelationGrid } from '../components/charts/CorrelationGrid'
import {
  Button,
  Card,
  CardTitle,
  CaveatList,
  EmptyState,
  ErrorState,
  Spinner,
} from '../components/ui/Primitives'
import { fetchAnalytics } from '../lib/api'
import { percent, ratio } from '../lib/format'
import { useAsync } from '../lib/useAsync'
import { usePortfolio } from '../state/PortfolioContext'

export function AnalyticsPage() {
  const { holdings, benchmark, lookbackDays, isEmpty, loadSample } = usePortfolio()

  const key = JSON.stringify({ holdings, benchmark, lookbackDays })
  const { data, error, loading, refetch } = useAsync(
    (options) => fetchAnalytics({ holdings, benchmark, lookbackDays }, options),
    [key],
    { enabled: !isEmpty },
  )

  return (
    <>
      <PageHeader
        eyebrow="Concentration / Risk"
        title="Analytics"
        subtitle="Where the risk actually sits, which is rarely where the money sits."
      />

      {isEmpty && (
        <EmptyState
          title="No portfolio to analyse"
          body="Add positions on the Portfolio page first."
          action={<Button variant="primary" onClick={loadSample}>Load a sample portfolio</Button>}
        />
      )}

      {!isEmpty && loading && !data && (
        <Card>
          <Spinner label="Computing concentration and risk decomposition…" />
        </Card>
      )}

      {!isEmpty && error && <ErrorState error={error} onRetry={refetch} />}

      {/* Held at reduced opacity while refetching rather than replaced by a
          skeleton — no layout jump when the window or holdings change. */}
      {!isEmpty && data && (
        <div className={loading ? 'opacity-45 transition-opacity duration-[--dur-base]' : ''}>
          <Results data={data} />
        </div>
      )}
    </>
  )
}

function Results({ data }) {
  const { concentration: c } = data

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricTile
          label="Effective holdings"
          value={ratio(c.effective_holdings, { decimals: 1 })}
          hint={`of ${c.n_holdings} positions`}
          emphasis
        />
        <MetricTile label="Concentration (HHI)" value={ratio(c.hhi, { decimals: 3 })} hint={c.label} emphasis />
        <MetricTile label="Largest position" value={percent(c.top_weight, { decimals: 1 })} hint={c.top_ticker} />
        <MetricTile label="Top 5 weight" value={percent(c.top_5_weight, { decimals: 1 })} />
      </div>

      <Card>
        <CardTitle hint="risk share vs capital share">Risk contribution</CardTitle>
        <p className="mb-4 max-w-[70ch] text-[12.5px] leading-relaxed text-ink-muted">
          A position&rsquo;s share of portfolio volatility rarely equals its share of value. A
          volatile, uncorrelated name can drive far more risk than its weight suggests — and a
          defensive one far less.
        </p>
        {/* Two series, so a legend is required — identity must never rest on
            colour-matching alone. */}
        <ul className="mb-3 flex flex-wrap items-center gap-4">
          {[
            { label: 'Share of value', color: 'var(--color-ink-ghost)' },
            { label: 'Share of risk', color: 'var(--color-viz-1)' },
          ].map((s) => (
            <li key={s.label} className="flex items-center gap-1.5 text-[11.5px] text-ink-muted">
              <span
                className="inline-block h-[3px] w-4 rounded-full"
                style={{ background: s.color }}
                aria-hidden="true"
              />
              {s.label}
            </li>
          ))}
        </ul>

        <ul className="flex flex-col gap-3">
          {data.risk_contribution.map((row) => (
            <RiskRow key={row.ticker} row={row} />
          ))}
        </ul>
      </Card>

      <Card>
        <CardTitle hint="daily returns over the window">Correlation</CardTitle>
        <p className="mb-4 max-w-[70ch] text-[12.5px] leading-relaxed text-ink-muted">
          Holdings that move together concentrate risk even when the position sizes look
          spread out. Warm cells move in step; cool cells move against each other.
        </p>
        <CorrelationGrid tickers={data.correlation.tickers} values={data.correlation.values} />
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardTitle hint="SIC-derived">Sector exposure</CardTitle>
          <ul className="flex flex-col gap-2.5">
            {data.sector_exposure.map((slice) => (
              <li key={slice.label} className="flex items-center gap-3">
                <span className="w-[168px] shrink-0 truncate text-[12.5px] text-ink-muted">
                  {slice.label}
                </span>
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                  <span
                    className="block h-full rounded-full bg-accent/70"
                    style={{ width: `${Math.max(slice.weight * 100, 1)}%` }}
                  />
                </span>
                <span className="w-[52px] shrink-0 text-right text-[12.5px] text-ink" data-numeric>
                  {percent(slice.weight, { decimals: 1 })}
                </span>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <CardTitle>Volatility</CardTitle>
          <div className="grid gap-3 sm:grid-cols-2">
            <MetricTile label="Realized" value={percent(data.realized_volatility)} hint="actual weight drift" />
            <MetricTile label="Model" value={percent(data.portfolio_volatility)} hint="today's weights" />
          </div>
        </Card>
      </div>

      <CaveatList caveats={data.caveats} />
    </div>
  )
}

function RiskRow({ row }) {
  const over = row.risk_premium > 0
  const max = 0.6

  return (
    <li className="flex items-center gap-3">
      <span className="w-[62px] shrink-0 text-[13px] font-medium text-ink">{row.ticker}</span>

      <div className="flex flex-1 flex-col gap-1">
        <Bar label="value" value={row.weight} max={max} tone="bg-[var(--color-ink-ghost)]" />
        <Bar label="risk" value={row.pct_of_risk} max={max} tone="bg-[var(--color-viz-1)]" />
      </div>

      <span
        className={[
          'w-[74px] shrink-0 text-right text-[12.5px]',
          over ? 'text-warn' : 'text-ink-faint',
        ].join(' ')}
        data-numeric
      >
        {percent(row.risk_premium, { sign: true, decimals: 1 })}
      </span>
    </li>
  )
}

function Bar({ label, value, max, tone }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-[38px] text-[10px] uppercase tracking-wider text-ink-ghost">{label}</span>
      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
        <span
          className={['block h-full rounded-full', tone].join(' ')}
          style={{ width: `${Math.min((value / max) * 100, 100)}%` }}
        />
      </span>
      <span className="w-[46px] text-right text-[11.5px] text-ink-muted" data-numeric>
        {percent(value, { decimals: 1 })}
      </span>
    </div>
  )
}
