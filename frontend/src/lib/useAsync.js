import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Runs an async function and tracks its state.
 *
 * Aborts the in-flight request whenever inputs change or the component
 * unmounts, which matters here because portfolio requests are slow on a cold
 * cache: without it, editing holdings quickly lets an older, slower response
 * land after a newer one and overwrite it with stale numbers.
 */
export function useAsync(fn, deps, { enabled = true } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: enabled })
  const controllerRef = useRef(null)
  const callbackRef = useRef(fn)
  callbackRef.current = fn

  const run = useCallback(() => {
    controllerRef.current?.abort()

    if (!enabled) {
      setState({ data: null, error: null, loading: false })
      return
    }

    const controller = new AbortController()
    controllerRef.current = controller

    setState((prev) => ({ ...prev, loading: true, error: null }))

    callbackRef
      .current({ signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setState({ data, error: null, loading: false })
      })
      .catch((error) => {
        if (controller.signal.aborted || error.name === 'AbortError') return
        setState({ data: null, error, loading: false })
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps])

  useEffect(() => {
    run()
    return () => controllerRef.current?.abort()
  }, [run])

  return { ...state, refetch: run }
}
