import { useLayoutEffect, useRef, useState } from 'react'

/**
 * Measures a container so the SVG can be drawn at real pixel width.
 *
 * The initial measurement is taken synchronously from the layout rather than
 * waiting on ResizeObserver. RO callbacks are driven by the rendering pipeline,
 * so in a background or non-compositing tab the first callback can be delayed
 * indefinitely and the chart stays frozen at its fallback width. RO is still
 * used, but only for subsequent resizes.
 */
export function useChartWidth(fallback = 640) {
  const ref = useRef(null)
  const [width, setWidth] = useState(fallback)

  useLayoutEffect(() => {
    const node = ref.current
    if (!node) return undefined

    const measure = () => {
      const next = node.getBoundingClientRect().width
      if (next > 0) setWidth((prev) => (Math.abs(prev - next) > 0.5 ? next : prev))
    }

    measure()

    const observer = new ResizeObserver(measure)
    observer.observe(node)
    window.addEventListener('resize', measure)

    return () => {
      observer.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [])

  return [ref, width]
}
