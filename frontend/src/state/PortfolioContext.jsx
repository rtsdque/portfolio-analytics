/**
 * The portfolio, held in localStorage.
 *
 * There is no account system and no server-side persistence — this is the only
 * place a user's holdings exist. That is a deliberate privacy property: the
 * backend stores nothing personal, only cached public market data.
 *
 * The consequence to respect: clearing browser data destroys the portfolio, so
 * writes must be robust and a corrupt payload must degrade to an empty
 * portfolio rather than crashing the app on boot.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

const STORAGE_KEY = 'portfolio.v1'

const DEFAULT_STATE = {
  holdings: [],
  benchmark: 'SPY',
  lookbackDays: 730,
}

const PortfolioContext = createContext(null)

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_STATE

    const parsed = JSON.parse(raw)
    if (!parsed || !Array.isArray(parsed.holdings)) return DEFAULT_STATE

    return {
      holdings: parsed.holdings
        .filter((h) => h && typeof h.ticker === 'string' && Number(h.shares) > 0)
        .map((h) => ({
          ticker: h.ticker.toUpperCase(),
          shares: Number(h.shares),
          costBasis: h.costBasis != null ? Number(h.costBasis) : null,
        })),
      benchmark: typeof parsed.benchmark === 'string' ? parsed.benchmark : DEFAULT_STATE.benchmark,
      lookbackDays: Number(parsed.lookbackDays) || DEFAULT_STATE.lookbackDays,
    }
  } catch {
    // A corrupt or unreadable payload must never prevent the app from starting.
    return DEFAULT_STATE
  }
}

export function PortfolioProvider({ children }) {
  const [state, setState] = useState(load)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    } catch {
      // Private browsing and full quotas both throw. Losing persistence is
      // survivable; crashing on every keystroke is not.
    }
  }, [state])

  /**
   * Adds a lot, merging into an existing position rather than replacing it.
   *
   * Buying more of something you already hold accumulates shares and produces a
   * share-weighted average cost — 40 @ $150 plus 10 @ $200 is 50 @ $160, which
   * is how a brokerage reports average cost.
   *
   * This previously overwrote the row outright, so adding a second lot silently
   * destroyed the first: 40 @ $150 then 10 @ $200 left you holding 10 shares,
   * with the other 40 gone and no warning.
   */
  const addHolding = useCallback((holding) => {
    setState((prev) => {
      const ticker = holding.ticker.trim().toUpperCase()
      const shares = Number(holding.shares)
      if (!ticker || !Number.isFinite(shares) || shares <= 0) return prev

      const costBasis =
        holding.costBasis != null && Number(holding.costBasis) > 0
          ? Number(holding.costBasis)
          : null

      const index = prev.holdings.findIndex((h) => h.ticker === ticker)
      if (index < 0) {
        return { ...prev, holdings: [...prev.holdings, { ticker, shares, costBasis }] }
      }

      const current = prev.holdings[index]
      const totalShares = current.shares + shares

      // An average is only meaningful when every lot has a price. If either
      // side is missing one, the combined basis is genuinely unknown — report
      // it as unknown rather than inventing a number from the half we have.
      const merged =
        current.costBasis != null && costBasis != null
          ? (current.shares * current.costBasis + shares * costBasis) / totalShares
          : null

      const next = [...prev.holdings]
      next[index] = { ticker, shares: totalShares, costBasis: merged }
      return { ...prev, holdings: next }
    })
  }, [])

  const removeHolding = useCallback((ticker) => {
    setState((prev) => ({
      ...prev,
      holdings: prev.holdings.filter((h) => h.ticker !== ticker),
    }))
  }, [])

  const updateHolding = useCallback((ticker, patch) => {
    setState((prev) => ({
      ...prev,
      holdings: prev.holdings.map((h) => (h.ticker === ticker ? { ...h, ...patch } : h)),
    }))
  }, [])

  const clearHoldings = useCallback(() => {
    setState((prev) => ({ ...prev, holdings: [] }))
  }, [])

  const setBenchmark = useCallback((benchmark) => {
    setState((prev) => ({ ...prev, benchmark: benchmark.trim().toUpperCase() }))
  }, [])

  const setLookbackDays = useCallback((lookbackDays) => {
    setState((prev) => ({ ...prev, lookbackDays: Number(lookbackDays) }))
  }, [])

  const loadSample = useCallback(() => {
    setState({
      holdings: [
        { ticker: 'AAPL', shares: 40, costBasis: 150 },
        { ticker: 'MSFT', shares: 15, costBasis: 310 },
        { ticker: 'NVDA', shares: 30, costBasis: 45 },
        { ticker: 'KO', shares: 120, costBasis: 58 },
        { ticker: 'JPM', shares: 25, costBasis: 185 },
      ],
      benchmark: 'SPY',
      lookbackDays: 730,
    })
  }, [])

  const value = useMemo(
    () => ({
      ...state,
      isEmpty: state.holdings.length === 0,
      hasAllCostBasis:
        state.holdings.length > 0 && state.holdings.every((h) => h.costBasis != null),
      addHolding,
      removeHolding,
      updateHolding,
      clearHoldings,
      setBenchmark,
      setLookbackDays,
      loadSample,
    }),
    [
      state,
      addHolding,
      removeHolding,
      updateHolding,
      clearHoldings,
      setBenchmark,
      setLookbackDays,
      loadSample,
    ],
  )

  return <PortfolioContext.Provider value={value}>{children}</PortfolioContext.Provider>
}

export function usePortfolio() {
  const context = useContext(PortfolioContext)
  if (!context) {
    throw new Error('usePortfolio must be used inside a PortfolioProvider')
  }
  return context
}
