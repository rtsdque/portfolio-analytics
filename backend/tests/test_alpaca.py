from datetime import date

import httpx
import pandas as pd
import pytest

from app.config import Settings
from app.providers.alpaca import AlpacaProvider, _chunk, _normalize
from app.providers.base import ProviderError, RateLimited, SubscriptionError, SymbolNotFound


def _settings(**overrides) -> Settings:
    base = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_feed": "sip",
        "_env_file": None,
    }
    return Settings(**{**base, **overrides})


def _bar(day: str, close: float) -> dict:
    return {"t": f"{day}T05:00:00Z", "o": close, "h": close, "l": close, "c": close, "v": 1}


def _provider(handler, **overrides) -> AlpacaProvider:
    settings = _settings(**overrides)
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=settings.alpaca_data_url,
        headers=settings.alpaca_headers,
    )
    return AlpacaProvider(settings=settings, client=client)


def test_missing_credentials_raise():
    with pytest.raises(ProviderError, match="credentials missing"):
        AlpacaProvider(settings=_settings(alpaca_api_key="", alpaca_secret_key=""))


def test_daily_closes_parsed_into_frame():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "bars": {
                    "AAPL": [_bar("2024-01-02", 185.0), _bar("2024-01-03", 184.0)],
                    "MSFT": [_bar("2024-01-02", 370.0), _bar("2024-01-03", 372.0)],
                },
                "next_page_token": None,
            },
        )

    with _provider(handler) as alpaca:
        frame = alpaca.get_daily_closes(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 1, 4))

    assert list(frame.columns) == ["AAPL", "MSFT"]
    assert frame.shape == (2, 2)
    assert frame["AAPL"].iloc[0] == pytest.approx(185.0)
    assert frame["MSFT"].iloc[-1] == pytest.approx(372.0)
    assert frame.index.name == "date"


def test_column_order_follows_requested_symbols():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "bars": {
                    "MSFT": [_bar("2024-01-02", 370.0)],
                    "AAPL": [_bar("2024-01-02", 185.0)],
                },
                "next_page_token": None,
            },
        )

    with _provider(handler) as alpaca:
        frame = alpaca.get_daily_closes(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 1, 4))

    assert list(frame.columns) == ["AAPL", "MSFT"]


def test_requests_adjusted_prices():
    """Unadjusted bars would show a 2-for-1 split as a 50% loss."""
    seen = {}

    def handler(request):
        seen.update(dict(request.url.params))
        return httpx.Response(
            200, json={"bars": {"AAPL": [_bar("2024-01-02", 185.0)]}, "next_page_token": None}
        )

    with _provider(handler) as alpaca:
        alpaca.get_daily_closes(["AAPL"], date(2024, 1, 1), date(2024, 1, 4))

    assert seen["adjustment"] == "all"
    assert seen["timeframe"] == "1Day"
    assert seen["feed"] == "sip"


def test_pagination_follows_next_page_token():
    calls = []

    def handler(request):
        calls.append(dict(request.url.params))
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={"bars": {"AAPL": [_bar("2024-01-02", 185.0)]}, "next_page_token": "page2"},
            )
        return httpx.Response(
            200, json={"bars": {"AAPL": [_bar("2024-01-03", 186.0)]}, "next_page_token": None}
        )

    with _provider(handler) as alpaca:
        frame = alpaca.get_daily_closes(["AAPL"], date(2024, 1, 1), date(2024, 1, 4))

    assert len(calls) == 2
    assert calls[1]["page_token"] == "page2"
    assert len(frame) == 2


def test_subscription_error_falls_back_to_iex():
    feeds = []

    def handler(request):
        feed = request.url.params.get("feed")
        feeds.append(feed)
        if feed == "sip":
            return httpx.Response(403, text='{"message":"subscription does not permit this"}')
        return httpx.Response(
            200, json={"bars": {"AAPL": [_bar("2024-01-02", 185.0)]}, "next_page_token": None}
        )

    with _provider(handler) as alpaca:
        frame = alpaca.get_daily_closes(["AAPL"], date(2024, 1, 1), date(2024, 1, 4))

    assert feeds == ["sip", "iex"]
    assert len(frame) == 1


def test_subscription_error_on_iex_is_not_retried():
    def handler(request):
        return httpx.Response(403, text='{"message":"subscription does not permit this"}')

    with _provider(handler, alpaca_feed="iex") as alpaca:
        with pytest.raises(SubscriptionError):
            alpaca.get_daily_closes(["AAPL"], date(2024, 1, 1), date(2024, 1, 4))


def test_bad_credentials_give_actionable_error():
    def handler(request):
        return httpx.Response(401, text='{"message":"access key verification failed"}')

    with _provider(handler) as alpaca:
        with pytest.raises(ProviderError, match="ALPACA_API_KEY"):
            alpaca.get_daily_closes(["AAPL"], date(2024, 1, 1), date(2024, 1, 4))


def test_rate_limit_raises_rate_limited():
    def handler(request):
        return httpx.Response(429, text="slow down")

    with _provider(handler) as alpaca:
        with pytest.raises(RateLimited):
            alpaca.get_daily_closes(["AAPL"], date(2024, 1, 1), date(2024, 1, 4))


def test_unknown_symbol_raises_rather_than_silently_dropping():
    """A typo'd ticker must not quietly vanish from the portfolio."""

    def handler(request):
        return httpx.Response(
            200, json={"bars": {"AAPL": [_bar("2024-01-02", 185.0)]}, "next_page_token": None}
        )

    with _provider(handler) as alpaca:
        with pytest.raises(SymbolNotFound, match="NOTREAL"):
            alpaca.get_daily_closes(["AAPL", "NOTREAL"], date(2024, 1, 1), date(2024, 1, 4))


def test_latest_prices():
    def handler(request):
        return httpx.Response(
            200, json={"bars": {"AAPL": {"c": 185.5}, "MSFT": {"c": 371.25}}}
        )

    with _provider(handler) as alpaca:
        latest = alpaca.get_latest_prices(["AAPL", "MSFT"])

    assert latest["AAPL"] == pytest.approx(185.5)
    assert list(latest.index) == ["AAPL", "MSFT"]


def test_latest_prices_missing_symbol_raises():
    def handler(request):
        return httpx.Response(200, json={"bars": {"AAPL": {"c": 185.5}}})

    with _provider(handler) as alpaca:
        with pytest.raises(SymbolNotFound, match="MSFT"):
            alpaca.get_latest_prices(["AAPL", "MSFT"])


def test_duplicate_bars_for_a_day_keep_the_last():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "bars": {"AAPL": [_bar("2024-01-02", 185.0), _bar("2024-01-02", 186.0)]},
                "next_page_token": None,
            },
        )

    with _provider(handler) as alpaca:
        frame = alpaca.get_daily_closes(["AAPL"], date(2024, 1, 1), date(2024, 1, 4))

    assert len(frame) == 1
    assert frame["AAPL"].iloc[0] == pytest.approx(186.0)


def test_rejects_empty_symbols():
    def handler(request):
        return httpx.Response(200, json={"bars": {}})

    with _provider(handler) as alpaca:
        with pytest.raises(ValueError, match="No symbols"):
            alpaca.get_daily_closes([], date(2024, 1, 1), date(2024, 1, 4))


def test_rejects_backwards_date_range():
    def handler(request):
        return httpx.Response(200, json={"bars": {}})

    with _provider(handler) as alpaca:
        with pytest.raises(ValueError, match="start must not be after end"):
            alpaca.get_daily_closes(["AAPL"], date(2024, 6, 1), date(2024, 1, 1))


@pytest.mark.parametrize(
    "raw,expected",
    [
        (["aapl", "MSFT"], ["AAPL", "MSFT"]),
        (["AAPL", "aapl", " AAPL "], ["AAPL"]),
        (["  spy "], ["SPY"]),
    ],
)
def test_normalize(raw, expected):
    assert _normalize(raw) == expected


def test_chunk_splits_large_requests():
    assert _chunk(list("abcde"), 2) == [["a", "b"], ["c", "d"], ["e"]]
