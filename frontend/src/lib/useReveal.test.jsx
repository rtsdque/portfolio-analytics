import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useReveal } from './useReveal'

/**
 * The reveal hook hides content with `opacity: 0` and depends on an observer
 * plus a CSS transition to bring it back. Both are driven by the rendering
 * pipeline, so in a background or non-compositing tab neither runs — and the
 * page comes up blank. These tests pin the guarantees that stop that.
 */

function Subject() {
  const ref = useReveal()
  return (
    <div ref={ref} data-reveal="" data-testid="subject">
      content
    </div>
  )
}

/**
 * Installs the real hiding rule from index.css.
 *
 * Without a stylesheet jsdom reports every element at opacity 1, and the
 * failsafe — which checks *rendered* opacity rather than trusting its own flag —
 * would never see anything hidden. Testing it without this would pass while
 * proving nothing.
 */
function installHidingRule() {
  document.documentElement.setAttribute('data-reveal-capable', '')
  const style = document.createElement('style')
  style.id = 'reveal-rule'
  style.textContent = `
    html[data-reveal-capable] [data-reveal]:not([data-revealed='true']) { opacity: 0; }
  `
  document.head.appendChild(style)
}

function stubRect({ onScreen }) {
  Element.prototype.getBoundingClientRect = vi.fn(() =>
    onScreen
      ? { top: 10, bottom: 200, left: 0, right: 100, width: 100, height: 190, x: 0, y: 10 }
      : { top: 5000, bottom: 5200, left: 0, right: 100, width: 100, height: 200, x: 0, y: 5000 },
  )
}

let originalRect

beforeEach(() => {
  originalRect = Element.prototype.getBoundingClientRect
  installHidingRule()
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  Element.prototype.getBoundingClientRect = originalRect
  document.getElementById('reveal-rule')?.remove()
  document.documentElement.removeAttribute('data-reveal-capable')
  vi.useRealTimers()
})

const opacityOf = (node) => parseFloat(getComputedStyle(node).opacity)

describe('useReveal', () => {
  it('the hiding rule actually applies in this environment', () => {
    // Guards the test itself: if this fails, every assertion below is vacuous.
    render(<div data-reveal="" data-testid="probe" />)
    expect(opacityOf(screen.getByTestId('probe'))).toBe(0)
  })

  it('reveals immediately when already in the viewport', () => {
    stubRect({ onScreen: true })
    render(<Subject />)

    const node = screen.getByTestId('subject')
    expect(node).toHaveAttribute('data-revealed', 'true')
    expect(opacityOf(node)).toBe(1)
  })

  it('leaves an offscreen element hidden up front', () => {
    stubRect({ onScreen: false })
    render(<Subject />)

    expect(screen.getByTestId('subject')).not.toHaveAttribute('data-revealed')
  })

  it('reveals when the observer reports the element in view', () => {
    stubRect({ onScreen: false })
    render(<Subject />)

    const observer = globalThis.ControllableIntersectionObserver.instances.at(-1)
    expect(observer).toBeDefined()
    observer.trigger(true)

    expect(screen.getByTestId('subject')).toHaveAttribute('data-revealed', 'true')
  })

  it('reveals via the failsafe when the observer never fires', async () => {
    // The exact failure seen in a non-compositing tab: the observer is
    // constructed, observes the element, and is never called back.
    stubRect({ onScreen: false })
    render(<Subject />)

    const node = screen.getByTestId('subject')
    expect(opacityOf(node)).toBe(0)

    vi.advanceTimersByTime(1000)

    await waitFor(() => expect(opacityOf(node)).toBe(1))
  })

  it('failsafe drops the element out of the hiding rule rather than trusting a transition', async () => {
    // Setting the flag alone is not enough: where the CSS transition also never
    // advances, opacity stays at 0. Removing `data-reveal` means no rule
    // matches, so visibility never depends on an animation running.
    stubRect({ onScreen: false })
    render(<Subject />)

    const node = screen.getByTestId('subject')
    vi.advanceTimersByTime(1000)

    await waitFor(() => expect(node).not.toHaveAttribute('data-reveal'))
    expect(opacityOf(node)).toBe(1)
  })

  it('reveals on mount under reduced motion', () => {
    const original = window.matchMedia
    window.matchMedia = (query) => ({
      matches: query.includes('prefers-reduced-motion'),
      media: query,
      addEventListener() {},
      removeEventListener() {},
    })

    try {
      stubRect({ onScreen: false })
      render(<Subject />)
      const node = screen.getByTestId('subject')

      expect(node).toHaveAttribute('data-revealed', 'true')
      expect(opacityOf(node)).toBe(1)
    } finally {
      window.matchMedia = original
    }
  })

  it('reveals on mount when IntersectionObserver is unavailable', () => {
    const original = globalThis.IntersectionObserver
    delete globalThis.IntersectionObserver

    try {
      stubRect({ onScreen: false })
      render(<Subject />)
      expect(opacityOf(screen.getByTestId('subject'))).toBe(1)
    } finally {
      globalThis.IntersectionObserver = original
    }
  })
})
