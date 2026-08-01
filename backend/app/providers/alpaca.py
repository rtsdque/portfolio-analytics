"""Alpaca market data provider.

Chosen over yfinance because it is an official, keyed, documented API. yfinance
scrapes endpoints Yahoo does not publish, and Yahoo rate-limits datacenter IP
ranges far harder than residential ones — code that works on a laptop returns
empty frames once it is deployed.

Feed selection matters on the free Basic plan:
  * ``sip`` is the full consolidated tape, available for data older than 15
    minutes. Daily bars are always older than that, so this is the right default.
  * ``iex`` is real-time but covers only IEX's ~2-3% of volume, so thin names get
    gappy bars and unreliable closes.

The client requests ``sip`` and falls back to ``iex`` automatically if the
account's plan rejects it.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import httpx
import pandas as pd

from app.config import Settings, get_settings
from app.providers.base import (
    InsufficientData,
    ProviderError,
    RateLimited,
    SubscriptionError,
    SymbolNotFound,
)

# Alpaca caps multi-symbol requests; batching keeps large portfolios working.
_MAX_SYMBOLS_PER_REQUEST = 100
_MAX_PAGES = 50


class AlpacaProvider:
    """Daily bars and latest prices from Alpaca's market data API."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        if not self._settings.has_alpaca_credentials:
            raise ProviderError(
                "Alpaca credentials missing. Set ALPACA_API_KEY and "
                "ALPACA_SECRET_KEY in backend/.env"
            )
        self._client = client or httpx.Client(
            base_url=self._settings.alpaca_data_url,
            headers=self._settings.alpaca_headers,
            timeout=self._settings.request_timeout,
        )

    # ---------------------------------------------------------------- requests

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Alpaca request failed: {exc}") from exc

        if response.status_code in (401, 403):
            body = response.text.lower()
            if "subscription" in body or "not permitted" in body:
                raise SubscriptionError(response.text)
            raise ProviderError(
                f"Alpaca rejected the credentials ({response.status_code}). "
                "Check ALPACA_API_KEY and ALPACA_SECRET_KEY in backend/.env"
            )
        if response.status_code == 429:
            raise RateLimited("Alpaca rate limit hit; back off and retry")
        if response.status_code >= 400:
            raise ProviderError(f"Alpaca returned {response.status_code}: {response.text[:300]}")

        return response.json()

    def _get_with_feed_fallback(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """Try the configured feed, then drop to iex if the plan disallows it."""
        try:
            return self._get(path, params)
        except SubscriptionError:
            if params.get("feed") == "iex":
                raise
            return self._get(path, {**params, "feed": "iex"})

    # -------------------------------------------------------------------- bars

    def get_daily_closes(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Split- and dividend-adjusted daily closes, one column per symbol.

        Adjusted closes are what return calculations need — an unadjusted series
        shows a 2-for-1 split as a 50% loss.
        """
        if not symbols:
            raise ValueError("No symbols requested")
        if start > end:
            raise ValueError("start must not be after end")

        frames: list[pd.DataFrame] = []
        for batch in _chunk(_normalize(symbols), _MAX_SYMBOLS_PER_REQUEST):
            frames.append(self._fetch_bars(batch, start, end))

        combined = pd.concat(frames, axis=1).sort_index()
        combined.index.name = "date"

        missing = [s for s in _normalize(symbols) if s not in combined.columns]
        if missing:
            raise SymbolNotFound(f"Alpaca returned no bars for: {sorted(missing)}")
        if combined.empty:
            raise InsufficientData("Alpaca returned no bars for the requested window")

        return combined[_normalize(symbols)]

    def _fetch_bars(self, symbols: list[str], start: date, end: date) -> pd.DataFrame:
        collected: dict[str, list[dict[str, Any]]] = {s: [] for s in symbols}
        page_token: str | None = None

        for _ in range(_MAX_PAGES):
            params: dict[str, Any] = {
                "symbols": ",".join(symbols),
                "timeframe": "1Day",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "adjustment": "all",
                "feed": self._settings.alpaca_feed,
                "limit": 10000,
            }
            if page_token:
                params["page_token"] = page_token

            payload = self._get_with_feed_fallback("/v2/stocks/bars", params)

            for symbol, bars in (payload.get("bars") or {}).items():
                collected.setdefault(symbol, []).extend(bars or [])

            page_token = payload.get("next_page_token")
            if not page_token:
                break
        else:
            raise ProviderError(
                f"Alpaca pagination exceeded {_MAX_PAGES} pages; narrow the date range"
            )

        series: dict[str, pd.Series] = {}
        for symbol, bars in collected.items():
            if not bars:
                continue
            index = pd.to_datetime([b["t"] for b in bars], utc=True).tz_convert(None).normalize()
            series[symbol] = pd.Series(
                [float(b["c"]) for b in bars], index=index, name=symbol
            ).groupby(level=0).last()

        if not series:
            return pd.DataFrame()
        return pd.DataFrame(series)

    # ------------------------------------------------------------------ latest

    def get_latest_prices(self, symbols: list[str]) -> pd.Series:
        """Most recent close per symbol."""
        if not symbols:
            raise ValueError("No symbols requested")

        out: dict[str, float] = {}
        for batch in _chunk(_normalize(symbols), _MAX_SYMBOLS_PER_REQUEST):
            payload = self._get_with_feed_fallback(
                "/v2/stocks/bars/latest",
                {"symbols": ",".join(batch), "feed": self._settings.alpaca_feed},
            )
            for symbol, bar in (payload.get("bars") or {}).items():
                if bar and bar.get("c") is not None:
                    out[symbol] = float(bar["c"])

        missing = [s for s in _normalize(symbols) if s not in out]
        if missing:
            raise SymbolNotFound(f"Alpaca returned no latest bar for: {sorted(missing)}")

        return pd.Series(out, dtype=float).reindex(_normalize(symbols))

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AlpacaProvider:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _normalize(symbols: list[str]) -> list[str]:
    """Upper-case, de-duplicated, order preserved."""
    seen: dict[str, None] = {}
    for symbol in symbols:
        seen.setdefault(symbol.strip().upper(), None)
    return list(seen)


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def utc_today() -> date:
    return datetime.now(timezone.utc).date()
