import { useEffect, useState } from 'react'

const QUERY = '(prefers-reduced-motion: reduce)'

/**
 * Whether the OS has asked for reduced motion.
 *
 * Ambient drift and parallax cause genuine nausea for people with vestibular
 * disorders, so this gates whether the animation loops run at all — not just
 * how fast they run. CSS also hides `[data-ambient]`, but the JS check matters
 * independently: a hidden canvas still burns a rAF loop every frame.
 */
export function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => typeof matchMedia !== 'undefined' && matchMedia(QUERY).matches,
  )

  useEffect(() => {
    const mq = matchMedia(QUERY)
    const onChange = (event) => setReduced(event.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  return reduced
}
