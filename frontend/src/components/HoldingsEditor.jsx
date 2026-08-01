import { useState } from 'react'

import { usePortfolio } from '../state/PortfolioContext'
import { currency, number } from '../lib/format'
import { IconPlus, IconTrash } from './layout/Icons'
import { Button, Card, CardTitle, Field, Input } from './ui/Primitives'

const BLANK = { ticker: '', shares: '', costBasis: '' }

export function HoldingsEditor() {
  const {
    holdings,
    benchmark,
    lookbackDays,
    addHolding,
    removeHolding,
    clearHoldings,
    setBenchmark,
    setLookbackDays,
    loadSample,
    isEmpty,
  } = usePortfolio()

  const [draft, setDraft] = useState(BLANK)
  const [error, setError] = useState(null)

  // Preview of the merged position, shown live while the form is being filled.
  const merge = (() => {
    const ticker = draft.ticker.trim().toUpperCase()
    const existing = holdings.find((h) => h.ticker === ticker)
    if (!existing) return null

    const added = Number(draft.shares)
    if (!Number.isFinite(added) || added <= 0) {
      return { ticker, shares: existing.shares, costBasis: existing.costBasis }
    }

    const cost = draft.costBasis === '' ? null : Number(draft.costBasis)
    const totalShares = existing.shares + added
    const averaged =
      existing.costBasis != null && cost != null && Number.isFinite(cost) && cost > 0
        ? (existing.shares * existing.costBasis + added * cost) / totalShares
        : null

    return { ticker, shares: totalShares, costBasis: averaged }
  })()

  const submit = (event) => {
    event.preventDefault()

    const ticker = draft.ticker.trim().toUpperCase()
    const shares = Number(draft.shares)

    if (!ticker) return setError('Enter a ticker.')
    if (!/^[A-Z.-]{1,10}$/.test(ticker)) return setError('That does not look like a ticker.')
    if (!Number.isFinite(shares) || shares <= 0) return setError('Shares must be greater than zero.')

    const costBasis = draft.costBasis === '' ? null : Number(draft.costBasis)
    if (costBasis !== null && (!Number.isFinite(costBasis) || costBasis <= 0)) {
      return setError('Cost basis must be greater than zero, or left blank.')
    }

    addHolding({ ticker, shares, costBasis })
    setDraft(BLANK)
    setError(null)
  }

  return (
    <Card>
      <CardTitle hint={isEmpty ? undefined : `${holdings.length} held`}>Positions</CardTitle>

      {/* Three equal columns, then the action on its own full-width row. The
          panel is too narrow to hold three inputs and a button side by side, so
          this is a deliberate two-row layout rather than a wrapped one — the
          previous version wrapped mid-row and read as a mistake. */}
      <form onSubmit={submit}>
        <div className="grid grid-cols-3 gap-2.5">
          <Field label="Ticker">
            <Input
              value={draft.ticker}
              onChange={(e) => setDraft({ ...draft, ticker: e.target.value.toUpperCase() })}
              placeholder="AAPL"
              maxLength={10}
              autoComplete="off"
              spellCheck={false}
            />
          </Field>
          <Field label="Shares">
            <Input
              value={draft.shares}
              onChange={(e) => setDraft({ ...draft, shares: e.target.value })}
              placeholder="40"
              inputMode="decimal"
            />
          </Field>
          <Field label="Cost" hint="optional">
            <Input
              value={draft.costBasis}
              onChange={(e) => setDraft({ ...draft, costBasis: e.target.value })}
              placeholder="150.00"
              inputMode="decimal"
            />
          </Field>
        </div>

        <Button type="submit" variant="primary" className="mt-2.5 w-full">
          <IconPlus width={14} height={14} />
          Add position
        </Button>
      </form>

      {error && <p className="mt-2.5 text-[12.5px] text-loss">{error}</p>}

      {/* Adding a ticker you already hold merges the lots rather than replacing
          the row, so say so before the button is pressed — a share count
          silently changing underneath you is alarming otherwise. */}
      {!error && merge && (
        <p className="mt-2.5 text-[12.5px] text-ink-faint" data-numeric>
          Adds to your existing {merge.ticker}:{' '}
          <span className="text-ink-muted">
            {number(merge.shares)} sh
            {merge.costBasis != null ? ` at ${currency(merge.costBasis)} average` : ''}
          </span>
        </p>
      )}

      {isEmpty ? (
        <div className="mt-5 rounded-[10px] border border-dashed border-line px-4 py-6 text-center">
          <p className="text-[13px] text-ink-muted">No positions yet.</p>
          <Button className="mt-3" onClick={loadSample}>
            Load a sample portfolio
          </Button>
        </div>
      ) : (
        <>
          {/* One shared grid template for the header and every row, so the
              columns line up by construction rather than by eye. Figures are
              right-aligned and tabular, which is what makes a column of numbers
              scannable — ragged left-aligned decimals are not. */}
          <div className="mt-5">
            <div
              className={[
                'grid items-center gap-3 border-b border-line-faint pb-1.5',
                'grid-cols-[1fr_auto_auto_20px]',
                'text-[10px] font-medium uppercase tracking-[0.1em] text-ink-ghost',
              ].join(' ')}
            >
              <span>Ticker</span>
              <span className="w-[68px] text-right">Shares</span>
              <span className="w-[76px] text-right">Cost</span>
              <span aria-hidden="true" />
            </div>

            <ul className="flex flex-col divide-y divide-line-faint">
              {holdings.map((holding) => (
                <li
                  key={holding.ticker}
                  className="group grid grid-cols-[1fr_auto_auto_20px] items-center gap-3 py-2.5"
                >
                  <span className="truncate text-[13.5px] font-medium text-ink">
                    {holding.ticker}
                  </span>
                  <span className="w-[68px] text-right text-[13px] text-ink-muted" data-numeric>
                    {number(holding.shares, { decimals: holding.shares % 1 ? 2 : 0 })}
                  </span>
                  <span
                    className={[
                      'w-[76px] text-right text-[13px]',
                      holding.costBasis == null ? 'text-ink-ghost' : 'text-ink-muted',
                    ].join(' ')}
                    data-numeric
                  >
                    {holding.costBasis == null ? '—' : currency(holding.costBasis)}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeHolding(holding.ticker)}
                    aria-label={`Remove ${holding.ticker}`}
                    className="rounded-md text-ink-ghost opacity-0 transition-[opacity,color,transform] duration-[--dur-quick] hover:text-loss focus-visible:opacity-100 group-hover:opacity-100 active:scale-90"
                  >
                    <IconTrash width={14} height={14} />
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-5 border-t border-line-faint pt-5">
            <div className="grid grid-cols-2 gap-2.5">
              <Field label="Benchmark">
                <Input
                  value={benchmark}
                  onChange={(e) => setBenchmark(e.target.value)}
                  maxLength={10}
                  spellCheck={false}
                />
              </Field>
              <Field label="Window">
                <select
                  value={lookbackDays}
                  onChange={(e) => setLookbackDays(e.target.value)}
                  className="h-[38px] w-full rounded-[--radius-control] border border-line bg-surface-2 px-3 text-[13.5px] text-ink transition-colors duration-[--dur-quick] hover:border-line-strong focus:border-accent focus:outline-none"
                >
                  <option value={182}>6 months</option>
                  <option value={365}>1 year</option>
                  <option value={730}>2 years</option>
                  <option value={1095}>3 years</option>
                  <option value={1825}>5 years</option>
                </select>
              </Field>
            </div>

            <div className="mt-3 flex justify-end">
              <Button variant="ghost" onClick={clearHoldings}>
                Clear all
              </Button>
            </div>
          </div>
        </>
      )}
    </Card>
  )
}
