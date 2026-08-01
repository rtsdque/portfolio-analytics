import { useEffect, useRef } from 'react'

import { useReducedMotion } from './useReducedMotion'

// If an element is still not actually painted by now, stop animating and show it.
const FAILSAFE_MS = 900

/**
 * Reveals an element once as it scrolls into view.
 *
 * Unobserves after the first reveal — an element that re-animates every time it
 * scrolls past is distracting, and on a page of figures it reads as the numbers
 * themselves changing.
 *
 * The hidden state is `opacity: 0`, so a reveal that never lands is a blank
 * page rather than a missing flourish. Four independent guarantees, because
 * each one covers a failure the others do not:
 *
 *   1. `html[data-reveal-capable]` gates the hiding rule and is set
 *      synchronously in main.jsx. If the bundle never executes, nothing hides.
 *   2. Reduced motion, or no IntersectionObserver — revealed on mount.
 *   3. Already in the viewport at mount — revealed from layout immediately,
 *      rather than waiting on an async callback.
 *   4. A failsafe that checks *rendered opacity*, not just the flag, and hard-
 *      reveals if the element is still invisible. This is the one that matters
 *      in practice: IntersectionObserver callbacks AND CSS transitions are both
 *      driven by the rendering pipeline, so in a background or non-compositing
 *      tab the flag can flip correctly and the opacity still never move.
 */
export function useReveal({ threshold = 0.12, rootMargin = '0px 0px -40px 0px' } = {}) {
  const ref = useRef(null)
  const reduced = useReducedMotion()

  useEffect(() => {
    const node = ref.current
    if (!node) return undefined

    /** Animated: flip the flag and let the transition carry it. */
    const reveal = () => {
      if (ref.current) ref.current.dataset.revealed = 'true'
    }

    /** Hard: drop out of the hiding rule entirely, no transition involved. */
    const revealNow = () => {
      const target = ref.current
      if (!target) return
      target.dataset.revealed = 'true'
      target.removeAttribute('data-reveal')
    }

    let observer = null

    if (reduced || typeof IntersectionObserver === 'undefined') {
      revealNow()
    } else {
      const rect = node.getBoundingClientRect()
      const onScreen = rect.top < window.innerHeight && rect.bottom > 0

      if (onScreen) {
        reveal()
      } else {
        observer = new IntersectionObserver(
          ([entry]) => {
            if (entry.isIntersecting) {
              entry.target.dataset.revealed = 'true'
              observer.unobserve(entry.target)
            }
          },
          { threshold, rootMargin },
        )
        observer.observe(node)
      }
    }

    // Armed on every path, including the animated ones — the check is whether
    // the element is actually painted, not whether we think we revealed it.
    const failsafe = setTimeout(() => {
      const target = ref.current
      if (!target) return
      if (parseFloat(getComputedStyle(target).opacity) < 0.99) {
        revealNow()
        observer?.disconnect()
      }
    }, FAILSAFE_MS)

    return () => {
      clearTimeout(failsafe)
      observer?.disconnect()
    }
  }, [reduced, threshold, rootMargin])

  return ref
}
