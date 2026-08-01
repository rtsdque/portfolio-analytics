import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PortfolioProvider, usePortfolio } from './PortfolioContext'

const wrapper = ({ children }) => <PortfolioProvider>{children}</PortfolioProvider>

const setup = () => renderHook(() => usePortfolio(), { wrapper })

describe('addHolding', () => {
  it('adds a new position', () => {
    const { result } = setup()
    act(() => result.current.addHolding({ ticker: 'AAPL', shares: 40, costBasis: 150 }))

    expect(result.current.holdings).toEqual([{ ticker: 'AAPL', shares: 40, costBasis: 150 }])
  })

  it('merges a second lot and share-weights the cost basis', () => {
    // Regression: this used to REPLACE the row, so buying more silently
    // destroyed the original position — 40 shares became 10 with no warning.
    const { result } = setup()
    act(() => result.current.addHolding({ ticker: 'AAPL', shares: 40, costBasis: 150 }))
    act(() => result.current.addHolding({ ticker: 'AAPL', shares: 10, costBasis: 200 }))

    expect(result.current.holdings).toHaveLength(1)
    expect(result.current.holdings[0].shares).toBe(50)
    expect(result.current.holdings[0].costBasis).toBeCloseTo(160, 10)
  })

  it('weights the average by shares, not by lot count', () => {
    const { result } = setup()
    act(() => result.current.addHolding({ ticker: 'KO', shares: 90, costBasis: 50 }))
    act(() => result.current.addHolding({ ticker: 'KO', shares: 10, costBasis: 150 }))

    // A naive mean of the two prices would give 100; the weighted answer is 60.
    expect(result.current.holdings[0].costBasis).toBeCloseTo(60, 10)
  })

  it('accumulates across three lots', () => {
    const { result } = setup()
    act(() => result.current.addHolding({ ticker: 'MSFT', shares: 10, costBasis: 100 }))
    act(() => result.current.addHolding({ ticker: 'MSFT', shares: 10, costBasis: 200 }))
    act(() => result.current.addHolding({ ticker: 'MSFT', shares: 20, costBasis: 250 }))

    expect(result.current.holdings[0].shares).toBe(40)
    expect(result.current.holdings[0].costBasis).toBeCloseTo(200, 10)
  })

  it('reports an unknown basis rather than inventing one from a partial lot', () => {
    const { result } = setup()
    act(() => result.current.addHolding({ ticker: 'AAPL', shares: 40, costBasis: 150 }))
    act(() => result.current.addHolding({ ticker: 'AAPL', shares: 10 }))

    expect(result.current.holdings[0].shares).toBe(50)
    expect(result.current.holdings[0].costBasis).toBeNull()
    expect(result.current.hasAllCostBasis).toBe(false)
  })

  it('normalizes case and whitespace before matching', () => {
    const { result } = setup()
    act(() => result.current.addHolding({ ticker: 'AAPL', shares: 40, costBasis: 150 }))
    act(() => result.current.addHolding({ ticker: '  aapl ', shares: 10, costBasis: 200 }))

    expect(result.current.holdings).toHaveLength(1)
    expect(result.current.holdings[0].shares).toBe(50)
  })

  it('ignores invalid input rather than corrupting the position', () => {
    const { result } = setup()
    act(() => result.current.addHolding({ ticker: 'AAPL', shares: 40, costBasis: 150 }))

    act(() => result.current.addHolding({ ticker: 'AAPL', shares: 0 }))
    act(() => result.current.addHolding({ ticker: 'AAPL', shares: -5 }))
    act(() => result.current.addHolding({ ticker: '', shares: 10 }))

    expect(result.current.holdings).toEqual([{ ticker: 'AAPL', shares: 40, costBasis: 150 }])
  })
})

describe('persistence', () => {
  it('round-trips through localStorage', () => {
    const first = setup()
    act(() => first.result.current.addHolding({ ticker: 'NVDA', shares: 5, costBasis: 45 }))

    const second = setup()
    expect(second.result.current.holdings).toEqual([{ ticker: 'NVDA', shares: 5, costBasis: 45 }])
  })

  it('degrades to empty rather than crashing on a corrupt payload', () => {
    localStorage.setItem('portfolio.v1', '{ this is not json')
    const { result } = setup()

    expect(result.current.holdings).toEqual([])
    expect(result.current.isEmpty).toBe(true)
  })

  it('discards malformed rows but keeps the good ones', () => {
    localStorage.setItem(
      'portfolio.v1',
      JSON.stringify({
        holdings: [
          { ticker: 'AAPL', shares: 10, costBasis: 100 },
          { ticker: 'BAD', shares: 0 },
          { shares: 5 },
          null,
        ],
        benchmark: 'SPY',
        lookbackDays: 730,
      }),
    )
    const { result } = setup()

    expect(result.current.holdings).toEqual([{ ticker: 'AAPL', shares: 10, costBasis: 100 }])
  })
})

describe('other mutations', () => {
  it('removes a holding', () => {
    const { result } = setup()
    act(() => result.current.addHolding({ ticker: 'AAPL', shares: 1 }))
    act(() => result.current.addHolding({ ticker: 'KO', shares: 2 }))
    act(() => result.current.removeHolding('AAPL'))

    expect(result.current.holdings.map((h) => h.ticker)).toEqual(['KO'])
  })

  it('loads a sample with a full cost basis', () => {
    const { result } = setup()
    act(() => result.current.loadSample())

    expect(result.current.holdings.length).toBeGreaterThan(1)
    expect(result.current.hasAllCostBasis).toBe(true)
  })

  it('upper-cases the benchmark', () => {
    const { result } = setup()
    act(() => result.current.setBenchmark(' qqq '))

    expect(result.current.benchmark).toBe('QQQ')
  })
})
