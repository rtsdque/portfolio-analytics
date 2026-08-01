import '@testing-library/jest-dom/vitest'

// jsdom implements neither observer. Both are supplied here as controllable
// stubs rather than no-ops, because the behaviour worth testing is precisely
// what happens when they DON'T fire — that is the failure that left every card
// on the page at zero opacity.

class ControllableIntersectionObserver {
  static instances = []

  constructor(callback, options) {
    this.callback = callback
    this.options = options
    this.elements = new Set()
    ControllableIntersectionObserver.instances.push(this)
  }

  observe(element) {
    this.elements.add(element)
  }

  unobserve(element) {
    this.elements.delete(element)
  }

  disconnect() {
    this.elements.clear()
  }

  /** Test hook: fire the callback as if the element scrolled into view. */
  trigger(isIntersecting = true) {
    for (const target of this.elements) {
      this.callback([{ target, isIntersecting }], this)
    }
  }
}

class StubResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.IntersectionObserver = ControllableIntersectionObserver
globalThis.ResizeObserver = StubResizeObserver
globalThis.ControllableIntersectionObserver = ControllableIntersectionObserver

// Default to "no reduced-motion preference" so the animated paths are the ones
// under test; individual tests override this.
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent() {
      return false
    },
  })
}

beforeEach(() => {
  ControllableIntersectionObserver.instances = []
  localStorage.clear()
})
