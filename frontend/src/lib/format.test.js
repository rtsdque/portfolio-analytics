import { describe, expect, it } from 'vitest'

import { currency, currencyCompact, direction, DASH, percent, ratio } from './format'

describe('direction', () => {
  /**
   * The accessibility contract. Roughly 8% of men cannot reliably separate red
   * from green, so colour is never allowed to be the only signal — the arrow
   * and the spoken label ship bundled with the token so a caller physically
   * cannot render one without the others.
   */
  it('bundles an arrow and a spoken label with every colour token', () => {
    for (const value of [0.12, -0.12, 0]) {
      const d = direction(value)
      expect(d.token).toBeTruthy()
      expect(d.label).toBeTruthy()
    }
  })

  it('distinguishes up and down by arrow, not only by colour', () => {
    expect(direction(0.12).arrow).toBe('▲')
    expect(direction(-0.12).arrow).toBe('▼')
    expect(direction(0.12).arrow).not.toBe(direction(-0.12).arrow)
  })

  it('uses distinct colour tokens for gain and loss', () => {
    expect(direction(1).token).toBe('text-gain')
    expect(direction(-1).token).toBe('text-loss')
  })

  it('treats missing values as unknown rather than flat', () => {
    for (const missing of [null, undefined, NaN]) {
      expect(direction(missing).key).toBe('unknown')
      expect(direction(missing).label).toBe('unavailable')
    }
  })

  it('reports exact zero as unchanged with no arrow', () => {
    expect(direction(0).key).toBe('flat')
    expect(direction(0).arrow).toBe('')
  })
})

describe('missing values', () => {
  /**
   * The API returns null for anything genuinely unknown — a missing Sharpe and
   * a Sharpe of 0.0 are different facts. Formatters must never render a null as
   * a zero.
   */
  it.each([
    ['currency', currency],
    ['percent', percent],
    ['ratio', ratio],
    ['currencyCompact', currencyCompact],
  ])('%s renders a dash, never a zero', (_name, fn) => {
    for (const missing of [null, undefined, NaN]) {
      expect(fn(missing)).toBe(DASH)
    }
    expect(fn(0)).not.toBe(DASH)
  })
})

describe('percent', () => {
  it('treats the input as a fraction', () => {
    expect(percent(0.2233)).toBe('22.33%')
  })

  it('shows an explicit sign when asked', () => {
    expect(percent(0.05, { sign: true })).toBe('+5.00%')
    expect(percent(-0.05, { sign: true })).toBe('-5.00%')
  })

  it('omits a sign on zero even in signed mode', () => {
    expect(percent(0, { sign: true })).toBe('0.00%')
  })
})

describe('currencyCompact', () => {
  it.each([
    [1_147_500_000_000, '$1.1T'],
    [58_900_000_000, '$58.9B'],
    [284_700_000, '$284.7M'],
    [12_400, '$12.4K'],
  ])('formats %s as %s', (input, expected) => {
    expect(currencyCompact(input)).toBe(expected)
  })

  it('handles negatives, which EBIT can be', () => {
    expect(currencyCompact(-9_200_000_000)).toBe('$-9.2B')
  })
})
