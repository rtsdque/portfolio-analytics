/** Scale and tick helpers shared by the chart components. */

export function extent(values) {
  let min = Infinity
  let max = -Infinity
  for (const v of values) {
    if (!Number.isFinite(v)) continue
    if (v < min) min = v
    if (v > max) max = v
  }
  if (min === Infinity) return [0, 1]
  if (min === max) return [min - 1, max + 1]
  return [min, max]
}

export function linear(domain, range) {
  const [d0, d1] = domain
  const [r0, r1] = range
  const span = d1 - d0 || 1
  return (value) => r0 + ((value - d0) / span) * (r1 - r0)
}

/**
 * Ticks on round numbers (0 / 1,000 / 2,000) rather than raw domain edges.
 * Axis ticks carry every value that isn't directly labelled, so they need to be
 * readable, not merely accurate.
 */
export function niceTicks([min, max], count = 5) {
  const span = max - min
  if (!Number.isFinite(span) || span <= 0) return [min]

  const rawStep = span / Math.max(count - 1, 1)
  const magnitude = 10 ** Math.floor(Math.log10(rawStep))
  const normalized = rawStep / magnitude
  const step =
    magnitude * (normalized >= 7.5 ? 10 : normalized >= 3.5 ? 5 : normalized >= 1.5 ? 2 : 1)

  const start = Math.ceil(min / step) * step
  const ticks = []
  for (let v = start; v <= max + step * 1e-6; v += step) {
    ticks.push(Math.abs(v) < step * 1e-6 ? 0 : v)
  }
  return ticks
}

export function timestamp(point) {
  return Date.parse(`${point.date}T00:00:00Z`)
}

/**
 * A polyline path. Straight segments — smoothing would invent values between
 * observations that were never in the data.
 *
 * `x` maps a point to a pixel via its DATE, not its array position. Extrema-
 * preserving downsampling leaves points unevenly spaced in time, so positioning
 * by index would stretch and compress the time axis arbitrarily.
 */
export function linePath(points, x, y) {
  return points
    .map((p, i) => `${i ? 'L' : 'M'}${x(p).toFixed(2)},${y(p.value).toFixed(2)}`)
    .join('')
}

export function areaPath(points, x, y, baseline) {
  if (!points.length) return ''
  const top = linePath(points, x, y)
  const lastX = x(points[points.length - 1]).toFixed(2)
  const firstX = x(points[0]).toFixed(2)
  return `${top}L${lastX},${baseline.toFixed(2)}L${firstX},${baseline.toFixed(2)}Z`
}

/** Point nearest a pixel position — for crosshair snapping. */
export function nearestPoint(px, x, points) {
  if (!points.length) return null
  let best = points[0]
  let bestDistance = Infinity
  for (const point of points) {
    const distance = Math.abs(x(point) - px)
    if (distance < bestDistance) {
      bestDistance = distance
      best = point
    }
  }
  return best
}

/**
 * Point nearest a given time.
 *
 * Each series is downsampled independently, so two series on the same chart do
 * not share array indices or even the same dates. The crosshair therefore snaps
 * on time and each series resolves its own nearest observation — indexing every
 * series by the first one's position would read the wrong values.
 */
export function nearestByTime(points, target) {
  if (!points.length) return null
  let best = points[0]
  let bestDistance = Infinity
  for (const point of points) {
    const distance = Math.abs(timestamp(point) - target)
    if (distance < bestDistance) {
      bestDistance = distance
      best = point
    }
  }
  return best
}

/**
 * Thin a series for rendering while preserving its extremes.
 *
 * Every bucket contributes its minimum AND maximum point, in original order,
 * so the drawn line always touches the true high and low of the series.
 *
 * This replaced plain stride sampling, which silently skipped extremes: on a
 * three-year window the drawdown chart bottomed out at -16.13% while the
 * headline above it read -17.99%, and at ten years the gap was 2.2 points. A
 * chart that contradicts its own stated number is worse than no chart.
 */
export function downsample(points, max = 320) {
  if (points.length <= max) return points

  const first = points[0]
  const last = points[points.length - 1]
  const inner = points.slice(1, -1)

  // Each bucket yields up to two points, so budget half as many buckets.
  const buckets = Math.max(Math.floor((max - 2) / 2), 1)
  const size = inner.length / buckets

  const out = [first]
  for (let b = 0; b < buckets; b += 1) {
    const from = Math.floor(b * size)
    // The final bucket is clamped to the exact end rather than computed.
    // `Math.floor((b + 1) * size)` loses the last element to floating-point
    // error — 159 * (1498 / 159) evaluates to 1497.9999999999998 — which
    // dropped the second-to-last observation and, with it, any extreme that
    // happened to land there.
    const to = b === buckets - 1 ? inner.length : Math.min(Math.floor((b + 1) * size), inner.length)
    if (to <= from) continue

    let lo = from
    let hi = from
    for (let i = from + 1; i < to; i += 1) {
      if (inner[i].value < inner[lo].value) lo = i
      if (inner[i].value > inner[hi].value) hi = i
    }

    // Emit in the order they occur so the line never doubles back on itself.
    const [a, z] = lo <= hi ? [lo, hi] : [hi, lo]
    out.push(inner[a])
    if (z !== a) out.push(inner[z])
  }
  out.push(last)

  return out
}
