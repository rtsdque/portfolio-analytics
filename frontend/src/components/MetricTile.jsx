import { direction, isMissing } from '../lib/format'

/**
 * A single labelled figure.
 *
 * When `delta` is supplied the tile shows an arrow and an explicit sign beside
 * the colour, so direction survives for anyone who cannot separate the two hues.
 * Screen readers get the direction spelled out in words.
 */
export function MetricTile({ label, value, delta, hint, emphasis = false }) {
  const showDirection = !isMissing(delta)
  const dir = direction(delta)

  return (
    <div className="flex flex-col gap-1 rounded-[--radius-card] border border-line-faint bg-surface-1/70 px-4 py-3.5">
      <p className="text-[10.5px] font-medium uppercase tracking-[0.12em] text-ink-faint">
        {label}
      </p>
      {/* Proportional figures, not tabular. Equal-width digits make a value
          like 121 look loose at display sizes; tabular-nums belongs in columns
          that must align vertically — table rows and axis ticks. */}
      <p
        className={[
          'leading-none tracking-[-0.02em] text-ink',
          emphasis ? 'text-[26px] font-semibold' : 'text-[20px] font-medium',
        ].join(' ')}
      >
        {value}
      </p>

      {showDirection && hint ? (
        <p className={['flex items-center gap-1 text-[12px]', dir.token].join(' ')} data-numeric>
          {dir.arrow && <span aria-hidden="true">{dir.arrow}</span>}
          <span>{hint}</span>
          <span className="sr-only">{dir.label}</span>
        </p>
      ) : (
        hint && <p className="text-[11.5px] text-ink-ghost">{hint}</p>
      )}
    </div>
  )
}
