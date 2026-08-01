/**
 * Formatting for financial figures.
 *
 * The API returns raw numbers — fractions stay fractions, currency stays float,
 * unknowns are null. All presentation happens here, in one place, so a change to
 * how money is displayed is a one-file change rather than a hunt.
 *
 * `direction()` is the accessibility contract: every gain/loss figure gets a
 * sign and an arrow alongside its colour. Roughly 8% of men cannot reliably
 * separate red from green, so colour alone is never allowed to be the only
 * carrier of whether money went up or down.
 */

const DASH = '—'

export function isMissing(value) {
  return value === null || value === undefined || Number.isNaN(value)
}

export function currency(value, { decimals = 2, sign = false } = {}) {
  if (isMissing(value)) return DASH
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    signDisplay: sign ? 'exceptZero' : 'auto',
  }).format(value)
}

/** Large figures as $1.14T / $58.9B / $284.7M. */
export function currencyCompact(value, { decimals = 1 } = {}) {
  if (isMissing(value)) return DASH
  const abs = Math.abs(value)
  const units = [
    [1e12, 'T'],
    [1e9, 'B'],
    [1e6, 'M'],
    [1e3, 'K'],
  ]
  for (const [scale, suffix] of units) {
    if (abs >= scale) {
      return `$${(value / scale).toFixed(decimals)}${suffix}`
    }
  }
  return currency(value, { decimals: 0 })
}

/** Fraction to percent. `percent(0.2233)` -> "22.33%". */
export function percent(value, { decimals = 2, sign = false } = {}) {
  if (isMissing(value)) return DASH
  return new Intl.NumberFormat('en-US', {
    style: 'percent',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    signDisplay: sign ? 'exceptZero' : 'auto',
  }).format(value)
}

export function ratio(value, { decimals = 2 } = {}) {
  if (isMissing(value)) return DASH
  return value.toFixed(decimals)
}

export function number(value, { decimals = 0 } = {}) {
  if (isMissing(value)) return DASH
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
}

/**
 * Classify a value as up / down / flat / unknown.
 *
 * Returns the arrow and screen-reader word alongside the token name, so callers
 * physically cannot render the colour without also having the redundant cues to
 * hand.
 */
export function direction(value, { threshold = 0 } = {}) {
  if (isMissing(value)) {
    return { key: 'unknown', arrow: '', label: 'unavailable', token: 'text-ink-faint' }
  }
  if (value > threshold) {
    return { key: 'up', arrow: '▲', label: 'up', token: 'text-gain' }
  }
  if (value < -threshold) {
    return { key: 'down', arrow: '▼', label: 'down', token: 'text-loss' }
  }
  return { key: 'flat', arrow: '', label: 'unchanged', token: 'text-flat' }
}

const ZONE_TOKENS = {
  Safe: 'text-zone-safe',
  Grey: 'text-zone-grey',
  Distress: 'text-zone-distress',
}

export function zoneToken(zone) {
  return ZONE_TOKENS[zone] ?? 'text-ink-muted'
}

const GRADE_TOKENS = {
  A: 'text-zone-safe',
  B: 'text-zone-safe',
  C: 'text-zone-grey',
  D: 'text-zone-distress',
  F: 'text-zone-distress',
}

export function gradeToken(grade) {
  return GRADE_TOKENS[grade] ?? 'text-ink-muted'
}

export function shortDate(value) {
  if (!value) return DASH
  return new Date(`${value}T00:00:00`).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export function monthYear(value) {
  if (!value) return DASH
  return new Date(`${value}T00:00:00`).toLocaleDateString('en-US', {
    month: 'short',
    year: '2-digit',
  })
}

export { DASH }
