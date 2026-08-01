/**
 * Backend client.
 *
 * The API surfaces structured errors ({code, message}) rather than bare HTTP
 * statuses, so ApiError carries the code through to the UI and a 404 on a
 * mistyped ticker can be told apart from the backend being down.
 */

export class ApiError extends Error {
  constructor(code, message, status) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

async function post(path, body, { signal } = {}) {
  let response
  try {
    response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new ApiError(
      'network_error',
      'Could not reach the analytics service. Is the backend running on port 8000?',
      0,
    )
  }

  let payload = null
  try {
    payload = await response.json()
  } catch {
    // Fall through to the status-based message below.
  }

  if (!response.ok) {
    // FastAPI validation failures come back as {detail: [...]}, which is
    // useful to a developer and meaningless to anyone else.
    if (response.status === 422 && Array.isArray(payload?.detail)) {
      const first = payload.detail[0]
      throw new ApiError('invalid_request', first?.msg ?? 'Invalid request', 422)
    }
    throw new ApiError(
      payload?.code ?? 'error',
      payload?.message ?? `Request failed (${response.status})`,
      response.status,
    )
  }

  return payload
}

const toHoldings = (holdings) =>
  holdings.map(({ ticker, shares, costBasis }) => ({
    ticker,
    shares,
    ...(costBasis != null && costBasis > 0 ? { cost_basis: costBasis } : {}),
  }))

export function fetchPortfolio({ holdings, benchmark, lookbackDays }, options) {
  return post(
    '/api/portfolio',
    {
      holdings: toHoldings(holdings),
      benchmark,
      lookback_days: lookbackDays,
    },
    options,
  )
}

export function fetchAnalytics({ holdings, benchmark, lookbackDays }, options) {
  return post(
    '/api/analytics',
    {
      holdings: toHoldings(holdings),
      benchmark,
      lookback_days: lookbackDays,
    },
    options,
  )
}

export function fetchCredit(symbols, options) {
  return post('/api/credit', { symbols }, options)
}

export function checkHealth() {
  return fetch('/api/health').then((r) => r.ok)
}
