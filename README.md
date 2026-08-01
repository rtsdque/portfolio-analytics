# Portfolio Analytics

A portfolio analytics workbench: share-weighted performance, risk decomposition,
and corporate credit assessment, built on live market data and SEC filings.

Three surfaces over one portfolio:

| Page | What it answers |
|---|---|
| **Portfolio** | What is it worth, what did it return, and which positions produced that return |
| **Analytics** | Where the risk actually sits — which is rarely where the money sits |
| **Credit Lab** | How two companies compare on bankruptcy risk, across three published models |

No accounts, no tracking, no server-side user data. Your portfolio lives in your
browser's `localStorage`; the backend database is a cache of public market and
filing data only.

## Stack

**Backend** — FastAPI, pandas, NumPy, SciPy, SQLAlchemy. The analytics core is
pure functions over passed-in data with no I/O, so every calculation is testable
offline.

There are deliberately no migrations. The only database is a cache of public
market and filing data — it holds nothing that cannot be re-fetched, so the
schema is created on startup and the file can be deleted at any time. Swapping
SQLite for Postgres in production is a `DATABASE_URL` change and nothing else.

**Frontend** — React 19, Vite, Tailwind CSS 4. Charts are hand-built inline SVG
rather than a charting library — the point was control over mark specs,
accessibility, and downsampling behaviour.

**Data** — Alpaca for prices, SEC EDGAR for fundamentals. Both free.

## Why these data sources

**Alpaca over yfinance.** yfinance scrapes endpoints Yahoo does not publish, and
Yahoo rate-limits datacenter IP ranges far harder than residential ones — code
that works on a laptop returns empty frames once deployed. Alpaca is official,
keyed, and documented.

**SEC EDGAR over a fundamentals vendor.** Alpaca is a brokerage API and has no
financial statements at all, so the Credit Lab could not be built on it. EDGAR
is the filings themselves: free, keyless, unlimited, and complete back a decade.
Sector classification falls out of the SIC codes already being fetched for
free — coarser than GICS, and labelled as such in the UI.

## Analytics

**Returns** — share-weighted valuation, total and annualized return, per-holding
attribution that reconciles exactly to the portfolio's return on cost.

**Risk** — volatility, Sharpe, Sortino, max drawdown with peak/trough/recovery
dates, beta, Jensen's alpha, tracking error, information ratio, historical VaR
and expected shortfall.

**Concentration** — Herfindahl index, effective holdings, sector exposure, a
correlation matrix, and risk contribution: each position's share of portfolio
volatility, which sums exactly to portfolio volatility.

**Credit** — published models rather than a fitted classifier, deliberately.
There is no freely available labelled bankruptcy dataset that maps onto
arbitrary live tickers, so a trained model would either learn from a stale
academic sample whose features do not match what filings expose, or fit on too
few default events to mean anything. These need no training data, are citable,
and can show their work:

- **Altman Z-Score** (1968) with the public-manufacturer, private, and
  non-manufacturer coefficient sets. The variant is chosen from the filer's SIC
  code; financials are excluded outright, because leverage is their business
  model and Altman's ratios are not interpretable for them.
- **Merton distance to default** via the Bharath–Shumway (2008) naive
  estimator, which forecasts default at least as well as iterating the full
  two-equation system.
- **Piotroski F-Score** (2000), reported as `score / evaluable` so a signal that
  could not be judged from a filer's tagged data is never mistaken for a signal
  that failed.

## Design notes

**Colour that carries data meaning is never reused as decoration.** Gain/loss
green and red belong to money moving; credit standing uses a separate blue /
amber / rose scale; violet is interactive chrome. A green button beside a green
number makes a reader stop and work out which green is which.

Palettes are validated rather than eyeballed — measured for lightness band,
chroma floor, contrast, and colour-blind separation in OKLab. That check caught
two collisions that looked fine by eye: the original "Safe" teal sat ΔE 8.8 from
gain green, below the perceptual floor.

**Colour is never the only channel.** Every gain/loss figure carries a sign and
an arrow, and the direction is exposed to screen readers in words.

**Every approximation is disclosed.** The API attaches a structured caveat to
any figure resting on an approximation or an inapplicable model, and the UI
renders them inline. Silent degradation is the failure mode that makes a finance
tool untrustworthy.

**Motion is opt-out and cheap.** Ambient effects animate only `transform` and
`opacity`; `backdrop-filter` is confined to fixed chrome. `prefers-reduced-motion`
stops the animation loops outright rather than merely hiding their output.

## Running it

Requires Python 3.11+, Node 18+, and a free Alpaca account (a paper-trading
account is enough — no funding, no live trading).

```bash
# backend
cd backend
python -m venv venv
venv/Scripts/activate        # Windows;  source venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env         # then fill in ALPACA_API_KEY, ALPACA_SECRET_KEY, SEC_USER_AGENT
uvicorn app.main:app --reload --port 8000
```

```bash
# frontend, in a second terminal
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

`SEC_USER_AGENT` must be a real contact string (`Name email@example.com`) — the
SEC returns 403 for requests that do not identify the caller.

## Tests

```bash
cd backend  && python -m pytest      # 174 tests
cd frontend && npm test              # 51 tests
```

The backend suite covers the analytics identities, both provider clients against
mocked transports, and the full API contract with fake providers, so it needs no
network access or API keys.

Several tests are regressions for bugs that only surfaced against real data or a
validator, and are worth reading as documentation of the traps:

- EDGAR's `fy` field is the fiscal year of the *report*, not of the fact — a
  10-K carries prior-year comparatives, so keying on it paired one year's
  balance sheet with another year's income statement.
- `CommonStockSharesIssued` is not shares outstanding; substituting it
  overstated Coca-Cola's share count by 60%.
- Chart downsampling by stride skipped extremes, so the drawdown chart
  contradicted the drawdown figure printed above it.
- CAGR annualized on a trading-day count rather than elapsed calendar time.
- A portfolio identical to its benchmark produced a tracking error of 1.5e-15
  rather than zero, and an information ratio of −0.81 out of pure noise.
- The SEC writes share classes as `BRK-B` where quote vendors write `BRK.B`, so
  every dual-class company was reported as "not an SEC filer".

## Disclaimer

Educational and analytical tool. Not investment advice, not a recommendation to
buy or sell any security, and not a substitute for professional judgement. The
credit models are published academic constructs with documented limitations —
Altman's Z-Score in particular flags manufacturers with captive finance arms as
distressed on balance-sheet leverage alone, which is why three models are shown
side by side and their disagreements are surfaced rather than averaged away.

## License

MIT
