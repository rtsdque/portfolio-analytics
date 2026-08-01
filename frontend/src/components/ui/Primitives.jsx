/**
 * Shared primitives.
 *
 * Motion here is limited to `transform` and `opacity` — both composited on the
 * GPU. Animating `box-shadow`, `filter`, or `backdrop-filter` forces paint on
 * every frame, and with live-updating figures on screen that is exactly where
 * jank shows up first.
 */

import { usePointerSheen, useMagnetic } from '../../lib/useMagnetic'
import { useReveal } from '../../lib/useReveal'
import { IconBlock, IconInfo, IconWarn } from '../layout/Icons'

/**
 * Surface card.
 *
 * `reveal` fades it in on scroll; `sheen` gives it a cursor-following highlight
 * and a hairline catch on hover. Both are opt-out (`reveal={false}`) for cards
 * that must be visible immediately, such as an error state.
 */
export function Card({ children, className = '', reveal = true, sheen = true, ...rest }) {
  const revealRef = useReveal()
  const sheenRef = usePointerSheen()

  // Two hooks, one node — merge their refs rather than nesting wrapper divs,
  // which would break the grid layouts these cards sit in.
  const setRefs = (node) => {
    revealRef.current = node
    sheenRef.current = node
  }

  return (
    <section
      ref={setRefs}
      data-reveal={reveal ? '' : undefined}
      className={[
        'rounded-[--radius-card] border border-line-faint bg-surface-1/70 p-5',
        'transition-colors duration-[--dur-base] hover:border-line',
        sheen ? 'sheen' : '',
        className,
      ].join(' ')}
      {...rest}
    >
      {children}
    </section>
  )
}

export function CardTitle({ children, hint }) {
  return (
    <div className="mb-4 flex items-baseline justify-between gap-3">
      <h2 className="text-[13px] font-semibold tracking-[-0.01em] text-ink">{children}</h2>
      {hint && <span className="text-[11px] text-ink-faint">{hint}</span>}
    </div>
  )
}

const BUTTON_VARIANTS = {
  primary:
    'bg-accent text-white hover:bg-accent-bright disabled:bg-surface-3 disabled:text-ink-ghost',
  secondary:
    'border border-line bg-surface-2 text-ink hover:border-line-strong hover:bg-surface-3 disabled:text-ink-ghost',
  ghost: 'text-ink-muted hover:bg-surface-1 hover:text-ink disabled:text-ink-ghost',
  danger: 'border border-line bg-surface-2 text-loss hover:border-loss/40 hover:bg-loss-dim',
}

/**
 * Button.
 *
 * Magnetic on fine pointers: it leans a few pixels toward the cursor, which
 * makes the target feel like it wants to be hit. The lean is written straight
 * to `style.transform` by the hook, so the press scale below is applied on an
 * inner span — otherwise the two would fight over the same property.
 */
export function Button({
  variant = 'secondary',
  magnetic = true,
  className = '',
  children,
  ...rest
}) {
  const ref = useMagnetic({ strength: magnetic ? 0.22 : 0, max: 4 })

  return (
    <button
      ref={ref}
      type="button"
      className={[
        'group inline-flex items-center justify-center rounded-[--radius-control]',
        'text-[13px] font-medium',
        'transition-[background-color,border-color,color] duration-[--dur-quick]',
        'will-change-transform disabled:cursor-not-allowed',
        BUTTON_VARIANTS[variant],
        className,
      ].join(' ')}
      {...rest}
    >
      <span
        className={[
          // 38px matches Input and the select, so a button sitting in a control
          // row lines up without per-instance height overrides.
          'inline-flex h-[38px] items-center justify-center gap-1.5 px-3',
          // The press is a scale, not a shadow change: cheap, composited, and
          // it reads as physical feedback rather than a colour flicker.
          // The easing goes through an arbitrary property — `var(--ease-spring)`
          // on its own is not a Tailwind class and was being emitted as a
          // literal class name, so the spring never applied.
          'transition-transform duration-[--dur-tap]',
          '[transition-timing-function:var(--ease-spring)]',
          'group-active:scale-[0.96] group-disabled:group-active:scale-100',
        ].join(' ')}
      >
        {children}
      </span>
    </button>
  )
}

/**
 * Labelled form control.
 *
 * The hint sits in the LABEL row, not beneath the input. Below the input it
 * added height to only the fields that had one, and since these rows align on
 * `items-end`, a single "Optional" under one field dragged the whole row's
 * baseline down — which is why the submit buttons sat lower than their inputs.
 * Keeping every field exactly the same height keeps rows level by construction.
 */
export function Field({ label, hint, children, className = '' }) {
  return (
    <label className={['flex min-w-0 flex-col gap-1.5', className].join(' ')}>
      <span className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-medium uppercase tracking-[0.1em] text-ink-faint">
          {label}
        </span>
        {hint && (
          <span className="text-[10px] lowercase tracking-normal text-ink-ghost">{hint}</span>
        )}
      </span>
      {children}
    </label>
  )
}

export function Input({ className = '', ...rest }) {
  return (
    <input
      className={[
        // Explicit height rather than padding-derived, so inputs, selects, and
        // buttons in the same row are guaranteed to match instead of happening
        // to match at one font size.
        'h-[38px] w-full rounded-[--radius-control] border border-line bg-surface-2 px-3',
        'text-[13.5px] text-ink placeholder:text-ink-ghost',
        'transition-colors duration-[--dur-quick]',
        'hover:border-line-strong focus:border-accent focus:outline-none',
        'tabular',
        className,
      ].join(' ')}
      {...rest}
    />
  )
}

const CAVEAT_STYLES = {
  info: { Icon: IconInfo, tone: 'text-note', ring: 'border-note/25 bg-note/[0.06]' },
  warning: { Icon: IconWarn, tone: 'text-warn', ring: 'border-warn/25 bg-warn/[0.06]' },
  blocking: { Icon: IconBlock, tone: 'text-block', ring: 'border-block/30 bg-block/[0.07]' },
}

/**
 * Renders a backend Caveat.
 *
 * These are not decorative. The API attaches one to every figure resting on an
 * approximation or an inapplicable model, and showing them is what keeps the
 * tool honest — a number with an unstated assumption is worse than no number.
 */
export function CaveatNote({ caveat, badge }) {
  const style = CAVEAT_STYLES[caveat.level] ?? CAVEAT_STYLES.info
  const { Icon } = style

  return (
    <div
      className={[
        'flex items-start gap-2.5 rounded-[10px] border px-3.5 py-2.5 text-[12.5px] leading-relaxed',
        style.ring,
      ].join(' ')}
    >
      <Icon className={['mt-[2px] shrink-0', style.tone].join(' ')} width={14} height={14} />
      {badge && (
        <span className="mt-[1px] shrink-0 rounded-full border border-line bg-surface-2 px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-ink-faint">
          {badge}
        </span>
      )}
      {/* Capped measure. The card spans the full page, but a 150-character line
          is not readable — the cap keeps the text at a sane width while the
          container still fills the row. */}
      <p className="max-w-[104ch] text-ink-muted">{caveat.message}</p>
    </div>
  )
}

export function CaveatList({ caveats, className = '' }) {
  if (!caveats?.length) return null
  return (
    <div className={['flex flex-col gap-2', className].join(' ')}>
      {caveats.map((caveat) => (
        <CaveatNote key={caveat.code} caveat={caveat} />
      ))}
    </div>
  )
}

export function Spinner({ label = 'Loading' }) {
  return (
    <div className="flex items-center gap-2.5 text-[13px] text-ink-faint" role="status">
      <svg width="15" height="15" viewBox="0 0 24 24" className="animate-spin" aria-hidden="true">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" opacity="0.18" fill="none" />
        <path
          d="M21 12a9 9 0 00-9-9"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          fill="none"
        />
      </svg>
      {label}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  return (
    <Card reveal={false} sheen={false} className="border-block/25 bg-block/[0.05]">
      <div className="flex items-start gap-3">
        <IconBlock className="mt-0.5 shrink-0 text-block" width={16} height={16} />
        <div className="flex-1">
          <p className="text-[13.5px] font-medium text-ink">Could not load this view</p>
          <p className="mt-1 text-[13px] text-ink-muted">{error.message}</p>
          {onRetry && (
            <Button className="mt-3" onClick={onRetry}>
              Try again
            </Button>
          )}
        </div>
      </div>
    </Card>
  )
}

export function EmptyState({ title, body, action }) {
  return (
    <Card className="flex flex-col items-center py-14 text-center">
      <p className="text-[15px] font-medium text-ink">{title}</p>
      <p className="mt-2 max-w-[46ch] text-[13px] leading-relaxed text-ink-muted">{body}</p>
      {action && <div className="mt-5">{action}</div>}
    </Card>
  )
}
