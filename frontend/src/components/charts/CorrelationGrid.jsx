import { useState } from 'react'

import { ratio } from '../../lib/format'

/**
 * Correlation matrix as a diverging heatmap.
 *
 * Diverging because correlation has a natural zero with opposite sides —
 * warm and cool poles with a neutral grey midpoint, so "no relationship"
 * reads as nothing. Deliberately not green/red: correlation is not profit and
 * loss, and reusing those hues here would make an unrelated scale look like
 * money moving.
 *
 * The cell values are printed, so this doubles as its own table view — the
 * colour is never the only way to read a number.
 */
export function CorrelationGrid({ tickers, values }) {
  const [hover, setHover] = useState(null)

  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-[2px] text-[11px]">
        <caption className="sr-only">
          Pairwise correlation of daily returns between holdings
        </caption>
        <thead>
          <tr>
            <th className="w-[52px]" />
            {tickers.map((t) => (
              <th
                key={t}
                scope="col"
                className="px-1 pb-1 text-center font-medium text-ink-faint"
              >
                {t}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tickers.map((rowTicker, i) => (
            <tr key={rowTicker}>
              <th
                scope="row"
                className="pr-2 text-right font-medium text-ink-faint whitespace-nowrap"
              >
                {rowTicker}
              </th>
              {tickers.map((colTicker, j) => {
                const value = values[i][j]
                const isDiagonal = i === j
                const isHovered = hover === `${i}-${j}`
                return (
                  <td
                    key={colTicker}
                    onMouseEnter={() => setHover(`${i}-${j}`)}
                    onMouseLeave={() => setHover(null)}
                    title={`${rowTicker} vs ${colTicker}: ${ratio(value)}`}
                    className="tabular h-[38px] w-[46px] rounded-[5px] text-center transition-[outline-color] duration-[--dur-quick]"
                    style={{
                      background: isDiagonal ? 'var(--color-surface-2)' : cellFill(value),
                      color: isDiagonal ? 'var(--color-ink-ghost)' : cellInk(value),
                      outline: isHovered ? '1px solid var(--color-line-strong)' : '1px solid transparent',
                    }}
                  >
                    {ratio(value)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <Legend />
    </div>
  )
}

/**
 * Equal steps per arm from a neutral midpoint. Opacity carries magnitude on a
 * single hue per side, which keeps each arm a one-hue ramp.
 */
function cellFill(value) {
  const magnitude = Math.min(Math.abs(value), 1)
  if (magnitude < 0.05) return 'var(--color-viz-mid)'
  const hue = value > 0 ? 'var(--color-viz-warm)' : 'var(--color-viz-cool)'
  return `color-mix(in oklab, ${hue} ${(magnitude * 78).toFixed(0)}%, var(--color-viz-mid))`
}

function cellInk(value) {
  return Math.abs(value) > 0.6 ? '#0b0b12' : 'var(--color-ink)'
}

function Legend() {
  const stops = [-1, -0.5, 0, 0.5, 1]
  return (
    <div className="mt-3 flex items-center gap-2">
      <span className="text-[10px] text-ink-ghost">-1.0</span>
      <span className="flex h-2 w-[128px] overflow-hidden rounded-full">
        {stops.map((stop, i) =>
          i < stops.length - 1 ? (
            <span
              key={stop}
              className="h-full flex-1"
              style={{
                background: `linear-gradient(90deg, ${cellFill(stop)}, ${cellFill(stops[i + 1])})`,
              }}
            />
          ) : null,
        )}
      </span>
      <span className="text-[10px] text-ink-ghost">+1.0</span>
      <span className="ml-2 text-[10.5px] text-ink-ghost">
        inverse · unrelated · moves together
      </span>
    </div>
  )
}
