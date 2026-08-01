import { describe, expect, it } from 'vitest'

import { downsample, linePath, nearestByTime, niceTicks, timestamp } from './scales'

/** A series of `n` points with a controllable trough and peak. */
function series(n, { troughAt, troughValue, peakAt, peakValue } = {}) {
  const out = []
  for (let i = 0; i < n; i += 1) {
    const day = String(i + 1).padStart(3, '0')
    const date = new Date(Date.UTC(2024, 0, 1 + i)).toISOString().slice(0, 10)
    let value = Math.sin(i / 9) * 2
    if (i === troughAt) value = troughValue
    if (i === peakAt) value = peakValue
    out.push({ date, value, day })
  }
  return out
}

describe('downsample', () => {
  it('returns the input untouched when it already fits', () => {
    const points = series(50)
    expect(downsample(points, 320)).toBe(points)
  })

  it('preserves the true minimum and maximum', () => {
    // Regression: stride sampling skipped the trough, so the drawdown chart
    // bottomed out at -16.13% under a headline reading -17.99%.
    const points = series(1500, {
      troughAt: 617,
      troughValue: -99,
      peakAt: 1181,
      peakValue: 42,
    })

    const out = downsample(points, 320)

    expect(Math.min(...out.map((p) => p.value))).toBe(-99)
    expect(Math.max(...out.map((p) => p.value))).toBe(42)
  })

  it('preserves extremes wherever they fall in the series', () => {
    // Index 1498 of 1500 is the regression case: floating-point error in the
    // final bucket boundary left the second-to-last observation unvisited.
    for (const at of [1, 7, 333, 800, 1234, 1497, 1498]) {
      const points = series(1500, { troughAt: at, troughValue: -1234 })
      const out = downsample(points, 320)
      expect(Math.min(...out.map((p) => p.value)), `trough at index ${at}`).toBe(-1234)
    }
  })

  it('visits every observation across a range of awkward series lengths', () => {
    // Bucket arithmetic is where off-by-one and float errors hide, so sweep
    // lengths that divide unevenly rather than trusting one convenient size.
    for (const n of [321, 400, 501, 640, 999, 1000, 1501, 2048, 5000]) {
      for (const at of [1, Math.floor(n / 2), n - 2]) {
        const points = series(n, { troughAt: at, troughValue: -777 })
        const out = downsample(points, 320)
        expect(Math.min(...out.map((p) => p.value)), `n=${n} trough=${at}`).toBe(-777)
      }
    }
  })

  it('keeps the first and last observation', () => {
    const points = series(1500)
    const out = downsample(points, 320)

    expect(out[0]).toBe(points[0])
    expect(out[out.length - 1]).toBe(points[points.length - 1])
  })

  it('stays chronological so the line never doubles back', () => {
    const points = series(1500, { troughAt: 900, troughValue: -50, peakAt: 400, peakValue: 90 })
    const out = downsample(points, 320)

    for (let i = 1; i < out.length; i += 1) {
      expect(timestamp(out[i])).toBeGreaterThanOrEqual(timestamp(out[i - 1]))
    }
  })

  it('respects the point budget', () => {
    const out = downsample(series(5000), 320)
    expect(out.length).toBeLessThanOrEqual(320)
    expect(out.length).toBeGreaterThan(100)
  })
})

describe('linePath', () => {
  it('positions points by date, not by array index', () => {
    // Unevenly spaced in time: two points a day apart, then a long gap.
    const points = [
      { date: '2024-01-01', value: 0 },
      { date: '2024-01-02', value: 1 },
      { date: '2024-12-31', value: 2 },
    ]
    const t0 = timestamp(points[0])
    const span = timestamp(points[2]) - t0
    const x = (p) => ((timestamp(p) - t0) / span) * 100
    const d = linePath(points, x, (v) => v)

    const xs = [...d.matchAll(/[ML]([\d.]+),/g)].map((m) => Number(m[1]))
    expect(xs[0]).toBeCloseTo(0, 5)
    expect(xs[2]).toBeCloseTo(100, 5)
    // Index positioning would put the middle point at 50; by date it is ~0.27.
    expect(xs[1]).toBeLessThan(1)
  })
})

describe('nearestByTime', () => {
  it('resolves each series against a timestamp rather than a shared index', () => {
    // Two series downsampled independently keep different observations.
    const a = [
      { date: '2024-01-01', value: 1 },
      { date: '2024-01-10', value: 2 },
      { date: '2024-01-20', value: 3 },
    ]
    const b = [
      { date: '2024-01-02', value: 10 },
      { date: '2024-01-19', value: 30 },
    ]

    const target = timestamp({ date: '2024-01-20' })
    expect(nearestByTime(a, target).value).toBe(3)
    expect(nearestByTime(b, target).value).toBe(30)
  })

  it('returns null for an empty series', () => {
    expect(nearestByTime([], 0)).toBeNull()
  })
})

describe('niceTicks', () => {
  it('produces round numbers', () => {
    for (const tick of niceTicks([0, 987], 5)) {
      expect(Number.isInteger(tick / 100) || Number.isInteger(tick / 200)).toBe(true)
    }
  })

  it('includes a zero tick when the domain spans zero', () => {
    expect(niceTicks([-0.19, 0], 5)).toContain(0)
  })

  it('survives a degenerate domain', () => {
    expect(niceTicks([5, 5], 5)).toEqual([5])
  })
})
