import { useState } from 'react'

import { PageHeader } from '../components/layout/AppShell'
import {
  Button,
  Card,
  CardTitle,
  CaveatList,
  ErrorState,
  Field,
  Input,
  Spinner,
} from '../components/ui/Primitives'
import { fetchCredit } from '../lib/api'
import {
  currencyCompact,
  gradeToken,
  percent,
  ratio,
  zoneToken,
} from '../lib/format'
import { useAsync } from '../lib/useAsync'

const Z_LABELS = {
  X1: 'Working capital / assets',
  X2: 'Retained earnings / assets',
  X3: 'EBIT / assets',
  X4: 'Market equity / liabilities',
  X5: 'Revenue / assets',
}

export function CreditLabPage() {
  const [draft, setDraft] = useState({ a: 'F', b: 'TSLA' })
  const [pair, setPair] = useState(['F', 'TSLA'])

  const { data, error, loading, refetch } = useAsync(
    (options) => fetchCredit(pair, options),
    [pair.join(',')],
    { enabled: pair.length > 0 },
  )

  const submit = (event) => {
    event.preventDefault()
    const next = [draft.a, draft.b]
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean)
    if (next.length) setPair([...new Set(next)])
  }

  return (
    <>
      <PageHeader
        eyebrow="Bankruptcy Risk / Head to head"
        title="Credit Lab"
        subtitle="Three published models — Altman, Merton, and Piotroski — run side by side. Where they disagree is the interesting part."
      />

      <Card className="mb-5">
        {/* Fixed equal columns and one shared control height, so the two inputs
            and the button sit on exactly the same baseline. */}
        <form
          onSubmit={submit}
          className="grid grid-cols-[minmax(0,160px)_minmax(0,160px)_auto] items-end gap-2.5"
        >
          <Field label="Company A">
            <Input
              value={draft.a}
              onChange={(e) => setDraft({ ...draft, a: e.target.value.toUpperCase() })}
              maxLength={10}
              spellCheck={false}
              placeholder="F"
            />
          </Field>
          <Field label="Company B" hint="optional">
            <Input
              value={draft.b}
              onChange={(e) => setDraft({ ...draft, b: e.target.value.toUpperCase() })}
              maxLength={10}
              spellCheck={false}
              placeholder="TSLA"
            />
          </Field>
          <Button type="submit" variant="primary" className="h-[38px] justify-self-start">
            Compare
          </Button>
        </form>
      </Card>

      {loading && (
        <Card>
          <Spinner label="Reading SEC filings and pricing default risk…" />
        </Card>
      )}

      {error && <ErrorState error={error} onRetry={refetch} />}

      {!loading && data && (
        <div className="grid items-start gap-5 lg:grid-cols-2">
          {data.companies.map((company) => (
            <CompanyCard key={company.symbol} company={company} />
          ))}
        </div>
      )}
    </>
  )
}

function CompanyCard({ company }) {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[19px] font-semibold tracking-[-0.02em] text-ink">
              {company.symbol}
            </p>
            <p className="mt-0.5 truncate text-[13px] text-ink-muted">{company.name}</p>
            <p className="mt-1 text-[11.5px] text-ink-ghost">
              {company.sector}
              {company.sic_description ? ` · ${company.sic_description}` : ''}
            </p>
          </div>

          {company.composite_grade ? (
            <div className="shrink-0 text-right">
              <p
                className={[
                  'font-display text-[46px] leading-none',
                  gradeToken(company.composite_grade),
                ].join(' ')}
              >
                {company.composite_grade}
              </p>
              <p className="mt-1 text-[11px] text-ink-faint" data-numeric>
                {ratio(company.composite_score, { decimals: 1 })} / 100
              </p>
            </div>
          ) : (
            <p className="shrink-0 rounded-full border border-line px-2.5 py-1 text-[11px] text-ink-faint">
              Not scoreable
            </p>
          )}
        </div>

        {company.financials && (
          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 border-t border-line-faint pt-4 text-[12.5px] sm:grid-cols-3">
            <Stat label="Market cap" value={currencyCompact(company.market_cap)} />
            <Stat label="Revenue" value={currencyCompact(company.financials.revenue)} />
            <Stat label="Total assets" value={currencyCompact(company.financials.total_assets)} />
            <Stat label="Liabilities" value={currencyCompact(company.financials.total_liabilities)} />
            <Stat label="EBIT" value={currencyCompact(company.financials.ebit)} />
            <Stat
              label="Fiscal year"
              value={`${company.financials.fiscal_year} · ${company.financials.form}`}
            />
          </dl>
        )}
      </Card>

      {company.z_score && <ZScoreCard z={company.z_score} />}
      {company.merton && <MertonCard m={company.merton} />}
      {company.piotroski && <PiotroskiCard p={company.piotroski} />}

      {/* Kept in the company's own column. A disclosure qualifies a specific
          result, and sitting directly beneath it is what makes that obvious —
          worth more than the extra line length a full-width row would buy.
          No company badge is needed here; the column already is the label.

          These are not a "bad score" marker: most fire on data availability,
          not results. Walmart scores B and still carries one, and JPMorgan is
          unscoreable purely because Altman does not apply to banks. */}
      <CaveatList caveats={company.caveats} />
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div>
      <dt className="text-[10.5px] uppercase tracking-[0.1em] text-ink-ghost">{label}</dt>
      <dd className="mt-0.5 text-ink" data-numeric>
        {value}
      </dd>
    </div>
  )
}

function ZScoreCard({ z }) {
  const total = Object.values(z.weighted).reduce((a, b) => a + Math.abs(b), 0)

  return (
    <Card>
      <CardTitle hint={z.variant.replace(/_/g, ' ')}>Altman Z-Score</CardTitle>
      <div className="flex items-baseline gap-3">
        <span className="tabular text-[30px] font-semibold leading-none text-ink" data-numeric>
          {ratio(z.score)}
        </span>
        <span className={['text-[14px] font-medium', zoneToken(z.zone)].join(' ')}>{z.zone}</span>
      </div>

      {/* The component breakdown is not optional detail. X4 routinely supplies
          most of the score, so a large market cap can carry a company into Safe
          on its own — that should be visible rather than inferred.

          Signed bars around a centre axis: direction carries the sign, so no
          colour is spent on it. An earlier version painted negative components
          in loss red, which put money-lost red beside a rose "Distress" badge
          in the same card — two different meanings in nearly the same hue. */}
      <ul className="mt-4 flex flex-col gap-2 border-t border-line-faint pt-3.5">
        {Object.entries(z.weighted).map(([key, weighted]) => {
          const share = Math.min((Math.abs(weighted) / total) * 100, 100)
          const negative = weighted < 0
          return (
            <li key={key} className="flex items-center gap-3 text-[12px]">
              <span className="w-[176px] shrink-0 text-ink-faint">{Z_LABELS[key] ?? key}</span>
              <span className="relative flex h-2 flex-1 items-center">
                <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-[var(--color-axis)]" />
                <span
                  className="absolute h-1.5 rounded-[3px]"
                  style={{
                    width: `${share / 2}%`,
                    left: negative ? undefined : '50%',
                    right: negative ? '50%' : undefined,
                    background: negative
                      ? 'var(--color-viz-2)'
                      : 'var(--color-viz-1)',
                  }}
                />
              </span>
              <span className="w-[52px] shrink-0 text-right text-ink-muted" data-numeric>
                {ratio(weighted)}
              </span>
            </li>
          )
        })}
      </ul>
      <p className="mt-2.5 text-[11px] text-ink-ghost">
        Left of the axis drags the score down; right lifts it.
      </p>
    </Card>
  )
}

function MertonCard({ m }) {
  return (
    <Card>
      <CardTitle hint="Bharath-Shumway naive estimator">Merton distance to default</CardTitle>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-[10.5px] uppercase tracking-[0.1em] text-ink-ghost">1-year PD</p>
          <p className="tabular mt-1 text-[26px] font-semibold leading-none text-ink" data-numeric>
            {percent(m.probability_of_default, { decimals: 2 })}
          </p>
        </div>
        <div>
          <p className="text-[10.5px] uppercase tracking-[0.1em] text-ink-ghost">Distance</p>
          <p className="tabular mt-1 text-[26px] font-semibold leading-none text-ink" data-numeric>
            {ratio(m.distance_to_default)}σ
          </p>
        </div>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 border-t border-line-faint pt-3.5 text-[12.5px] sm:grid-cols-3">
        <Stat label="Debt barrier" value={currencyCompact(m.debt_barrier)} />
        <Stat label="Asset vol" value={percent(m.asset_volatility, { decimals: 1 })} />
        <Stat label="Equity vol" value={percent(m.equity_volatility, { decimals: 1 })} />
      </dl>
    </Card>
  )
}

function PiotroskiCard({ p }) {
  return (
    <Card>
      <CardTitle hint={p.unavailable.length ? `${p.unavailable.length} unevaluable` : undefined}>
        Piotroski F-Score
      </CardTitle>
      <p className="tabular text-[26px] font-semibold leading-none text-ink" data-numeric>
        {p.score}
        <span className="text-[16px] font-normal text-ink-faint"> / {p.evaluable}</span>
      </p>

      <ul className="mt-4 flex flex-wrap gap-1.5">
        {Object.entries(p.signals).map(([name, fired]) => {
          const unknown = p.unavailable.includes(name)
          return (
            <li
              key={name}
              title={unknown ? 'Not evaluable from this filer’s tagged data' : undefined}
              className={[
                'rounded-full border px-2 py-0.5 text-[11px]',
                unknown
                  ? 'border-dashed border-line text-ink-ghost'
                  : fired
                    ? 'border-zone-safe/30 bg-zone-safe/10 text-zone-safe'
                    : 'border-line text-ink-faint',
              ].join(' ')}
            >
              {name.replace(/_/g, ' ')}
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
