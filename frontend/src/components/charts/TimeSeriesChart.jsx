import { useMemo, useState } from 'react'

import {
  areaPath,
  downsample,
  extent,
  linear,
  linePath,
  nearestByTime,
  nearestPoint,
  niceTicks,
  timestamp,
} from './scales'
import { useChartWidth } from './useChartWidth'

// The container height must include the x-axis band, or the card ends up with a
// tiny nested scrollbar because the plot fits and the labels don't.
const AXIS_BAND = 22
const PAD = { top: 12, right: 56, bottom: 6, left: 52 }

/**
 * Line / area chart over a shared date index.
 *
 * Every series must share the same x index — the backend already aligns them.
 * There is deliberately no second y-axis: two scales on one plot invent a
 * correlation that isn't in the data. Series that differ in magnitude are
 * indexed to a common base upstream instead.
 */
export function TimeSeriesChart({
  series,
  height = 220,
  formatValue,
  formatTick,
  formatDate,
  fill = false,
  zeroBaseline = false,
  labelEnd = true,
}) {
  const [ref, width] = useChartWidth()
  const [hover, setHover] = useState(null)

  const prepared = useMemo(
    () => series.map((s) => ({ ...s, points: downsample(s.points) })),
    [series],
  )

  const plotHeight = height - AXIS_BAND
  const innerWidth = Math.max(width - PAD.left - PAD.right, 10)
  const innerHeight = Math.max(plotHeight - PAD.top - PAD.bottom, 10)

  const length = prepared[0]?.points.length ?? 0
  const allValues = prepared.flatMap((s) => s.points.map((p) => p.value))

  const [rawMin, rawMax] = extent(allValues)
  const domain = zeroBaseline ? [Math.min(rawMin, 0), Math.max(rawMax, 0)] : [rawMin, rawMax]
  const ticks = niceTicks(domain, 5)
  const padded = [Math.min(domain[0], ticks[0]), Math.max(domain[1], ticks[ticks.length - 1])]

  // x is a TIME scale, not an index scale. Downsampling preserves extremes,
  // which leaves points unevenly spaced, so anything positioned by array index
  // would silently distort the date axis.
  const times = prepared.flatMap((s) => s.points.map(timestamp))
  const timeDomain = extent(times)
  const timeScale = linear(timeDomain, [PAD.left, PAD.left + innerWidth])
  const x = (point) => timeScale(timestamp(point))
  const yScale = linear(padded, [PAD.top + innerHeight, PAD.top])
  const baseline = yScale(zeroBaseline ? 0 : padded[0])

  if (length === 0) return <div ref={ref} style={{ height }} />

  // Hover is stored as a TIMESTAMP, not an index. Each series is downsampled
  // independently and may keep different observations, so an index valid for
  // one series would read the wrong row in another.
  const onMove = (event) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const snapped = nearestPoint(event.clientX - rect.left, x, prepared[0].points)
    setHover(snapped ? timestamp(snapped) : null)
  }

  const hoverPoints =
    hover == null ? null : prepared.map((s) => ({ series: s, point: nearestByTime(s.points, hover) }))
  const hoverX = hoverPoints?.[0]?.point ? x(hoverPoints[0].point) : null

  return (
    <div ref={ref} className="relative">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`${prepared.map((s) => s.label).join(' and ')} over time`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        className="block touch-none"
      >
        {/* Gridlines: solid hairlines one step off the surface. Never dashed —
            dashing reads as "projection" when it is only a grid. */}
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={PAD.left}
              x2={PAD.left + innerWidth}
              y1={yScale(tick)}
              y2={yScale(tick)}
              stroke={tick === 0 && zeroBaseline ? 'var(--color-axis)' : 'var(--color-grid)'}
              strokeWidth="1"
              shapeRendering="crispEdges"
            />
            <text
              x={PAD.left - 8}
              y={yScale(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              className="tabular fill-[var(--color-ink-ghost)] text-[10px]"
            >
              {formatTick(tick)}
            </text>
          </g>
        ))}

        {fill &&
          prepared.map((s) => (
            <path
              key={`${s.label}-fill`}
              d={areaPath(s.points, x, yScale, baseline)}
              fill={s.color}
              opacity="0.1"
            />
          ))}

        {prepared.map((s) => (
          <path
            key={s.label}
            d={linePath(s.points, x, yScale)}
            fill="none"
            stroke={s.color}
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeDasharray={s.dashed ? '5 4' : undefined}
          />
        ))}

        {/* Endpoint markers carry a 2px ring in the surface colour so they stay
            legible where they overlap. */}
        {labelEnd &&
          prepared.map((s) => {
            const last = s.points[s.points.length - 1]
            return (
              <circle
                key={`${s.label}-dot`}
                cx={x(last)}
                cy={yScale(last.value)}
                r="4"
                fill={s.color}
                stroke="var(--color-surface-1)"
                strokeWidth="2"
              />
            )
          })}

        {/* Labels selectively — the endpoint only. A value on every point is
            chaos and goes unread. Text wears an ink token, never the series
            colour; the coloured dot beside it carries identity. */}
        {labelEnd &&
          prepared.map((s) => {
            const last = s.points[s.points.length - 1]
            return (
              <text
                key={`${s.label}-label`}
                x={x(last) + 9}
                y={yScale(last.value)}
                dominantBaseline="middle"
                className="tabular fill-[var(--color-ink-muted)] text-[10.5px]"
              >
                {formatValue(last.value)}
              </text>
            )
          })}

        {hoverPoints && hoverX != null && (
          <>
            <line
              x1={hoverX}
              x2={hoverX}
              y1={PAD.top}
              y2={PAD.top + innerHeight}
              stroke="var(--color-line-strong)"
              strokeWidth="1"
            />
            {hoverPoints.map(({ series: s, point }) =>
              point ? (
                <circle
                  key={`${s.label}-hover`}
                  cx={x(point)}
                  cy={yScale(point.value)}
                  r="4"
                  fill={s.color}
                  stroke="var(--color-surface-1)"
                  strokeWidth="2"
                />
              ) : null,
            )}
          </>
        )}

        <line
          x1={PAD.left}
          x2={PAD.left + innerWidth}
          y1={PAD.top + innerHeight}
          y2={PAD.top + innerHeight}
          stroke="var(--color-axis)"
          strokeWidth="1"
          shapeRendering="crispEdges"
        />
      </svg>

      <div
        className="pointer-events-none flex justify-between px-[52px] text-[10px] text-ink-ghost"
        style={{ height: AXIS_BAND }}
      >
        <span>{formatDate(prepared[0].points[0].date)}</span>
        <span>{formatDate(prepared[0].points[prepared[0].points.length - 1].date)}</span>
      </div>

      {hoverPoints && hoverX != null && (
        <Tooltip
          left={hoverX}
          width={width}
          date={formatDate(hoverPoints[0].point.date)}
          rows={hoverPoints
            .filter(({ point }) => point)
            .map(({ series: s, point }) => ({
              label: s.label,
              color: s.color,
              value: formatValue(point.value),
            }))}
        />
      )}
    </div>
  )
}

function Tooltip({ left, width, date, rows }) {
  // Flip before the tooltip would run off the right edge.
  const flip = left > width - 150
  return (
    <div
      className="pointer-events-none absolute top-2 z-10 rounded-[10px] border border-line bg-raised/95 px-2.5 py-2 shadow-[var(--shadow-float)]"
      style={{ left: flip ? undefined : left + 12, right: flip ? width - left + 12 : undefined }}
    >
      <p className="mb-1 text-[10.5px] text-ink-ghost">{date}</p>
      {rows.map((row) => (
        <p key={row.label} className="flex items-center gap-2 text-[11.5px] whitespace-nowrap">
          <span
            className="inline-block h-[3px] w-3 shrink-0 rounded-full"
            style={{ background: row.color }}
            aria-hidden="true"
          />
          <span className="text-ink-muted">{row.label}</span>
          <span className="tabular ml-auto text-ink">{row.value}</span>
        </p>
      ))}
    </div>
  )
}

/** A legend is always present for two or more series; a single series needs none. */
export function ChartLegend({ series }) {
  if (series.length < 2) return null
  return (
    <ul className="mb-3 flex flex-wrap items-center gap-4">
      {series.map((s) => (
        <li key={s.label} className="flex items-center gap-1.5 text-[11.5px] text-ink-muted">
          <span
            className="inline-block h-[3px] w-4 rounded-full"
            style={{
              background: s.dashed
                ? `repeating-linear-gradient(90deg, ${s.color} 0 5px, transparent 5px 9px)`
                : s.color,
            }}
            aria-hidden="true"
          />
          {s.label}
        </li>
      ))}
    </ul>
  )
}
