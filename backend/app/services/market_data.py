"""Cached access to price data."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app import cache
from app.providers.base import PriceProvider


class MarketData:
    def __init__(self, provider: PriceProvider, session_factory) -> None:
        self._provider = provider
        self._session_factory = session_factory

    def daily_closes(self, symbols: list[str], start: date, end: date) -> pd.DataFrame:
        """Adjusted daily closes, served from cache where possible."""
        symbols = list(dict.fromkeys(s.strip().upper() for s in symbols))

        with self._session_factory() as session:
            stale = cache.symbols_needing_fetch(session, symbols, start, end)

            if stale:
                fetched = self._provider.get_daily_closes(stale, start, end)
                payload = {
                    symbol: {
                        idx.date(): float(value)
                        for idx, value in fetched[symbol].dropna().items()
                    }
                    for symbol in fetched.columns
                }
                cache.store_prices(session, payload, start, end)

            stored = cache.load_prices(session, symbols, start, end)

        frame = pd.DataFrame(
            {symbol: pd.Series(series) for symbol, series in stored.items() if series}
        )
        if frame.empty:
            return frame

        frame.index = pd.to_datetime(frame.index)
        frame = frame.sort_index()
        frame.index.name = "date"
        return frame[[s for s in symbols if s in frame.columns]]

    def latest_closes(self, symbols: list[str], start: date, end: date) -> pd.Series:
        """Most recent cached close per symbol.

        Deliberately derived from the daily series rather than a separate live
        quote call: it costs no extra request, and every figure on the page is
        then computed from one consistent snapshot instead of mixing a live
        price into metrics built on end-of-day bars.
        """
        frame = self.daily_closes(symbols, start, end)
        if frame.empty:
            return pd.Series(dtype=float)
        return frame.ffill().iloc[-1]
