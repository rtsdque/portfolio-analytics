import { useCallback, useEffect, useRef } from 'react'

import { useReducedMotion } from './useReducedMotion'

/**
 * Magnetic hover: the element leans a few pixels toward the cursor.
 *
 * Written against the DOM node directly rather than through React state — a
 * setState per pointermove would re-render the subtree on every mouse event.
 * This only ever writes `transform`, which the compositor handles without
 * layout or paint.
 *
 * Disabled entirely for reduced motion, and for coarse pointers where there is
 * no hover to respond to.
 */
export function useMagnetic({ strength = 0.28, max = 6 } = {}) {
  const ref = useRef(null)
  const reduced = useReducedMotion()

  const onPointerMove = useCallback(
    (event) => {
      const node = ref.current
      if (!node || reduced) return
      const rect = node.getBoundingClientRect()
      const dx = event.clientX - (rect.left + rect.width / 2)
      const dy = event.clientY - (rect.top + rect.height / 2)
      const x = Math.max(-max, Math.min(max, dx * strength))
      const y = Math.max(-max, Math.min(max, dy * strength))
      node.style.transform = `translate3d(${x.toFixed(2)}px, ${y.toFixed(2)}px, 0)`
    },
    [reduced, strength, max],
  )

  const onPointerLeave = useCallback(() => {
    const node = ref.current
    if (node) node.style.transform = ''
  }, [])

  useEffect(() => {
    const node = ref.current
    if (!node) return undefined
    if (reduced || !matchMedia('(hover: hover) and (pointer: fine)').matches) {
      node.style.transform = ''
      return undefined
    }

    node.addEventListener('pointermove', onPointerMove)
    node.addEventListener('pointerleave', onPointerLeave)
    return () => {
      node.removeEventListener('pointermove', onPointerMove)
      node.removeEventListener('pointerleave', onPointerLeave)
      node.style.transform = ''
    }
  }, [reduced, onPointerMove, onPointerLeave])

  return ref
}

/**
 * Tracks the cursor within an element as CSS custom properties, so a hover
 * sheen can follow the pointer.
 *
 * Sets `--px` / `--py` on the node; the sheen is a pseudo-element positioned
 * from those. Writing two custom properties is far cheaper than re-declaring a
 * radial-gradient background on every move, which would repaint the card.
 */
export function usePointerSheen() {
  const ref = useRef(null)
  const reduced = useReducedMotion()

  useEffect(() => {
    const node = ref.current
    if (!node || reduced) return undefined
    if (!matchMedia('(hover: hover) and (pointer: fine)').matches) return undefined

    let queued = false
    let lastEvent = null

    const flush = () => {
      queued = false
      if (!lastEvent || !ref.current) return
      const rect = ref.current.getBoundingClientRect()
      ref.current.style.setProperty('--px', `${lastEvent.clientX - rect.left}px`)
      ref.current.style.setProperty('--py', `${lastEvent.clientY - rect.top}px`)
    }

    // Coalesced to one write per frame; pointermove can fire far more often
    // than the display refreshes.
    const onMove = (event) => {
      lastEvent = event
      if (!queued) {
        queued = true
        requestAnimationFrame(flush)
      }
    }

    node.addEventListener('pointermove', onMove)
    return () => node.removeEventListener('pointermove', onMove)
  }, [reduced])

  return ref
}
