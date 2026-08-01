import { useEffect, useRef } from 'react'

import { useReducedMotion } from '../../lib/useReducedMotion'

/**
 * Drifting star field.
 *
 * Three parallax layers falling slowly from the top, each with a gentle
 * horizontal wander so the motion reads as drift rather than snow — straight
 * vertical descent at uniform speed is what makes a particle field look
 * seasonal instead of expensive.
 *
 * Deliberate constraints:
 *   * Canvas, not DOM nodes. ~90 animated elements would mean 90 composited
 *     layers and a style recalc every frame.
 *   * Paused when the tab is hidden — a background tab has no business
 *     spending frames on decoration.
 *   * Not rendered at all under reduced motion, and hidden by CSS besides.
 *   * Sits behind everything at low opacity and is `pointer-events: none`, so
 *     it can never interfere with reading a figure or hitting a control.
 */
export function StarField({ density = 0.00009, opacity = 0.5 }) {
  const canvasRef = useRef(null)
  const reduced = useReducedMotion()

  useEffect(() => {
    if (reduced) return undefined

    const canvas = canvasRef.current
    if (!canvas) return undefined
    const ctx = canvas.getContext('2d', { alpha: true })
    if (!ctx) return undefined

    let width = 0
    let height = 0
    let stars = []
    let frame = 0
    let running = true

    // Three depths: far stars are small, dim, and slow; near stars larger and
    // faster. The speed difference is what creates the parallax.
    const LAYERS = [
      { depth: 0.35, size: [0.5, 1.0], speed: [1.6, 3.2], alpha: [0.18, 0.4] },
      { depth: 0.65, size: [0.8, 1.5], speed: [3.4, 6.0], alpha: [0.3, 0.6] },
      { depth: 1.0, size: [1.1, 2.0], speed: [6.4, 10.0], alpha: [0.45, 0.85] },
    ]

    const rand = (min, max) => min + Math.random() * (max - min)

    const makeStar = (layer, seeded) => ({
      x: Math.random() * width,
      y: seeded ? Math.random() * height : -rand(4, 60),
      r: rand(...layer.size),
      // px per second, not per frame — so the drift is identical on 60Hz and
      // 144Hz displays.
      vy: rand(...layer.speed),
      baseAlpha: rand(...layer.alpha),
      wanderAmp: rand(2, 11),
      wanderRate: rand(0.05, 0.16),
      phase: Math.random() * Math.PI * 2,
      twinkleRate: rand(0.25, 0.8),
      warm: Math.random() < 0.22,
    })

    const build = () => {
      const target = Math.round(width * height * density)
      stars = []
      for (let i = 0; i < target; i += 1) {
        const layer = LAYERS[i % LAYERS.length]
        stars.push({ ...makeStar(layer, true), layer })
      }
    }

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = window.innerWidth
      height = window.innerHeight
      canvas.width = Math.floor(width * dpr)
      canvas.height = Math.floor(height * dpr)
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      build()
    }

    let last = performance.now()

    const draw = (now) => {
      if (!running) return
      const dt = Math.min((now - last) / 1000, 0.05)
      last = now
      const t = now / 1000

      ctx.clearRect(0, 0, width, height)

      for (const star of stars) {
        star.y += star.vy * dt
        if (star.y - star.r > height) {
          Object.assign(star, makeStar(star.layer, false), { layer: star.layer })
        }

        const wander = Math.sin(t * star.wanderRate * Math.PI + star.phase) * star.wanderAmp
        const twinkle = 0.72 + 0.28 * Math.sin(t * star.twinkleRate * Math.PI + star.phase)
        const alpha = star.baseAlpha * twinkle

        ctx.beginPath()
        ctx.arc(star.x + wander, star.y, star.r, 0, Math.PI * 2)
        ctx.fillStyle = star.warm
          ? `rgba(224, 196, 133, ${alpha.toFixed(3)})`
          : `rgba(201, 192, 255, ${alpha.toFixed(3)})`
        ctx.fill()
      }

      frame = requestAnimationFrame(draw)
    }

    const onVisibility = () => {
      if (document.hidden) {
        running = false
        cancelAnimationFrame(frame)
      } else if (!running) {
        running = true
        last = performance.now()
        frame = requestAnimationFrame(draw)
      }
    }

    resize()
    frame = requestAnimationFrame(draw)

    window.addEventListener('resize', resize)
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      running = false
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', resize)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [reduced, density])

  if (reduced) return null

  return (
    <canvas
      ref={canvasRef}
      data-ambient
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0"
      style={{ opacity }}
    />
  )
}
