import httpx
import pytest

from app.config import Settings
from app.providers.base import z_variant_for_sic
from app.providers.edgar import EdgarProvider
from app.providers.base import InsufficientData, ProviderError, SymbolNotFound

TICKER_MAP = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}


def _settings() -> Settings:
    return Settings(sec_user_agent="Test Suite test@example.com", _env_file=None)


def _instant(end, val, fy, filed, form="10-K"):
    return {"end": end, "val": val, "fy": fy, "fp": "FY", "form": form, "filed": filed}


def _period(start, end, val, fy, filed, form="10-K"):
    return {
        "start": start,
        "end": end,
        "val": val,
        "fy": fy,
        "fp": "FY",
        "form": form,
        "filed": filed,
    }


def _facts(**concepts) -> dict:
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                tag: {"units": {"USD": entries}} for tag, entries in concepts.items()
            }
        },
    }


def _provider(facts, submissions=None) -> EdgarProvider:
    submissions = submissions or {"name": "Apple Inc.", "sic": "3571", "sicDescription": "Computers"}

    def handler(request):
        path = request.url.path
        if "company_tickers" in path:
            return httpx.Response(200, json=TICKER_MAP)
        if "submissions" in path:
            return httpx.Response(200, json=submissions)
        if "companyfacts" in path:
            return httpx.Response(200, json=facts)
        return httpx.Response(404)

    settings = _settings()
    client = httpx.Client(transport=httpx.MockTransport(handler), headers=settings.sec_headers)
    return EdgarProvider(settings=settings, client=client)


# --------------------------------------------------------------------- the bug


def test_income_statement_is_paired_with_the_matching_balance_sheet():
    """Regression: EDGAR's `fy` is the *report's* fiscal year, not the fact's.

    A 10-K carries prior-year comparatives, so one `fy` bucket holds two
    different periods. Keying on `fy` paired Apple's 2024 balance sheet with its
    2023 income statement. Both revenue rows below sit in fy=2025.
    """
    facts = _facts(
        Assets=[
            _instant("2024-09-28", 365_000, fy=2025, filed="2024-11-01"),
            _instant("2023-09-30", 352_600, fy=2024, filed="2023-11-03"),
        ],
        Liabilities=[
            _instant("2024-09-28", 308_000, fy=2025, filed="2024-11-01"),
            _instant("2023-09-30", 290_400, fy=2024, filed="2023-11-03"),
        ],
        Revenues=[
            _period("2023-10-01", "2024-09-28", 391_000, fy=2025, filed="2024-11-01"),
            _period("2022-10-02", "2023-09-30", 383_300, fy=2025, filed="2024-11-01"),
        ],
        NetIncomeLoss=[
            _period("2023-10-01", "2024-09-28", 93_700, fy=2025, filed="2024-11-01"),
            _period("2022-10-02", "2023-09-30", 97_000, fy=2025, filed="2024-11-01"),
        ],
        StockholdersEquity=[_instant("2024-09-28", 57_000, fy=2025, filed="2024-11-01")],
    )

    with _provider(facts) as edgar:
        years = edgar.get_annual_financials("AAPL", years=2)

    latest = years[0]
    assert str(latest.period_end) == "2024-09-28"
    assert latest.fiscal_year == 2024
    assert latest.financials.total_assets == pytest.approx(365_000)
    assert latest.financials.revenue == pytest.approx(391_000)
    assert latest.financials.net_income == pytest.approx(93_700)

    prior = years[1]
    assert str(prior.period_end) == "2023-09-30"
    assert prior.financials.total_assets == pytest.approx(352_600)
    assert prior.financials.revenue == pytest.approx(383_300)


# ------------------------------------------------------------------- filtering


def test_quarterly_facts_are_excluded():
    facts = _facts(
        Assets=[_instant("2024-09-28", 365_000, fy=2024, filed="2024-11-01")],
        Revenues=[
            _period("2024-06-30", "2024-09-28", 94_900, fy=2024, filed="2024-11-01"),
            _period("2023-10-01", "2024-09-28", 391_000, fy=2024, filed="2024-11-01"),
        ],
        NetIncomeLoss=[_period("2023-10-01", "2024-09-28", 93_700, fy=2024, filed="2024-11-01")],
        StockholdersEquity=[_instant("2024-09-28", 57_000, fy=2024, filed="2024-11-01")],
    )

    with _provider(facts) as edgar:
        years = edgar.get_annual_financials("AAPL", years=1)

    # The 90-day span must lose to the 363-day one.
    assert years[0].financials.revenue == pytest.approx(391_000)


def test_non_annual_forms_are_excluded():
    facts = _facts(
        Assets=[
            _instant("2024-09-28", 365_000, fy=2024, filed="2024-11-01"),
            _instant("2024-06-29", 331_000, fy=2024, filed="2024-08-01", form="10-Q"),
        ],
        Revenues=[_period("2023-10-01", "2024-09-28", 391_000, fy=2024, filed="2024-11-01")],
        NetIncomeLoss=[_period("2023-10-01", "2024-09-28", 93_700, fy=2024, filed="2024-11-01")],
        StockholdersEquity=[_instant("2024-09-28", 57_000, fy=2024, filed="2024-11-01")],
    )

    with _provider(facts) as edgar:
        years = edgar.get_annual_financials("AAPL", years=5)

    assert len(years) == 1
    assert str(years[0].period_end) == "2024-09-28"


def test_restatement_prefers_the_later_filing():
    facts = _facts(
        Assets=[
            _instant("2024-09-28", 365_000, fy=2024, filed="2024-11-01"),
            _instant("2024-09-28", 366_500, fy=2024, filed="2025-02-15", form="10-K/A"),
        ],
        Revenues=[_period("2023-10-01", "2024-09-28", 391_000, fy=2024, filed="2024-11-01")],
        NetIncomeLoss=[_period("2023-10-01", "2024-09-28", 93_700, fy=2024, filed="2024-11-01")],
        StockholdersEquity=[_instant("2024-09-28", 57_000, fy=2024, filed="2024-11-01")],
    )

    with _provider(facts) as edgar:
        years = edgar.get_annual_financials("AAPL", years=1)

    assert years[0].financials.total_assets == pytest.approx(366_500)


# ------------------------------------------------------------------- derivation


def test_total_liabilities_derived_from_balance_sheet_identity():
    """Many filers tag equity but never tag Liabilities directly."""
    facts = _facts(
        Assets=[_instant("2024-09-28", 365_000, fy=2024, filed="2024-11-01")],
        Revenues=[_period("2023-10-01", "2024-09-28", 391_000, fy=2024, filed="2024-11-01")],
        NetIncomeLoss=[_period("2023-10-01", "2024-09-28", 93_700, fy=2024, filed="2024-11-01")],
        StockholdersEquity=[_instant("2024-09-28", 57_000, fy=2024, filed="2024-11-01")],
    )

    with _provider(facts) as edgar:
        fin = edgar.get_annual_financials("AAPL", years=1)[0].financials

    assert fin.total_liabilities == pytest.approx(365_000 - 57_000)


def test_ebit_derived_from_pretax_plus_interest():
    facts = _facts(
        Assets=[_instant("2024-12-31", 100_000, fy=2024, filed="2025-02-01")],
        Revenues=[_period("2024-01-01", "2024-12-31", 50_000, fy=2024, filed="2025-02-01")],
        NetIncomeLoss=[_period("2024-01-01", "2024-12-31", 5_000, fy=2024, filed="2025-02-01")],
        StockholdersEquity=[_instant("2024-12-31", 40_000, fy=2024, filed="2025-02-01")],
        IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest=[
            _period("2024-01-01", "2024-12-31", 6_500, fy=2024, filed="2025-02-01")
        ],
        InterestExpense=[_period("2024-01-01", "2024-12-31", 800, fy=2024, filed="2025-02-01")],
    )

    with _provider(facts) as edgar:
        fin = edgar.get_annual_financials("AAPL", years=1)[0].financials

    assert fin.ebit == pytest.approx(7_300)


def test_operating_income_preferred_over_derivation():
    facts = _facts(
        Assets=[_instant("2024-12-31", 100_000, fy=2024, filed="2025-02-01")],
        Revenues=[_period("2024-01-01", "2024-12-31", 50_000, fy=2024, filed="2025-02-01")],
        NetIncomeLoss=[_period("2024-01-01", "2024-12-31", 5_000, fy=2024, filed="2025-02-01")],
        StockholdersEquity=[_instant("2024-12-31", 40_000, fy=2024, filed="2025-02-01")],
        OperatingIncomeLoss=[_period("2024-01-01", "2024-12-31", 7_000, fy=2024, filed="2025-02-01")],
        InterestExpense=[_period("2024-01-01", "2024-12-31", 800, fy=2024, filed="2025-02-01")],
    )

    with _provider(facts) as edgar:
        fin = edgar.get_annual_financials("AAPL", years=1)[0].financials

    assert fin.ebit == pytest.approx(7_000)


def test_shares_issued_is_not_used_as_outstanding():
    """KO reports ~7.0B issued against ~4.3B outstanding; the gap is treasury."""
    facts = {
        "facts": {
            "us-gaap": {
                "Assets": {"units": {"USD": [_instant("2024-12-31", 100_000, 2024, "2025-02-01")]}},
                "Revenues": {
                    "units": {
                        "USD": [_period("2024-01-01", "2024-12-31", 47_000, 2024, "2025-02-01")]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [_period("2024-01-01", "2024-12-31", 10_600, 2024, "2025-02-01")]
                    }
                },
                "StockholdersEquity": {
                    "units": {"USD": [_instant("2024-12-31", 25_000, 2024, "2025-02-01")]}
                },
                "CommonStockSharesIssued": {
                    "units": {"shares": [_instant("2024-12-31", 7_040_000, 2024, "2025-02-01")]}
                },
            }
        }
    }

    with _provider(facts) as edgar:
        fin = edgar.get_annual_financials("AAPL", years=1)[0].financials

    assert fin.shares_outstanding is None


def test_cover_page_share_count_matched_by_proximity():
    """The dei count is dated at filing, weeks after the fiscal period end."""
    facts = {
        "facts": {
            "us-gaap": {
                "Assets": {"units": {"USD": [_instant("2024-12-31", 100_000, 2024, "2025-02-01")]}},
                "Revenues": {
                    "units": {
                        "USD": [_period("2024-01-01", "2024-12-31", 47_000, 2024, "2025-02-01")]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [_period("2024-01-01", "2024-12-31", 10_600, 2024, "2025-02-01")]
                    }
                },
                "StockholdersEquity": {
                    "units": {"USD": [_instant("2024-12-31", 25_000, 2024, "2025-02-01")]}
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {"end": "2025-02-10", "val": 4_300_000, "filed": "2025-02-14"},
                            {"end": "2024-02-12", "val": 4_320_000, "filed": "2024-02-16"},
                        ]
                    }
                }
            },
        }
    }

    with _provider(facts) as edgar:
        row = edgar.get_annual_financials("AAPL", years=1)[0]

    assert row.financials.shares_outstanding == pytest.approx(4_300_000)
    assert row.shares_source == "point_in_time"
    assert not row.shares_are_approximate


def _minimal_statements() -> dict:
    return {
        "Assets": {"units": {"USD": [_instant("2025-12-31", 289_200, 2025, "2026-02-11")]}},
        "Revenues": {
            "units": {"USD": [_period("2025-01-01", "2025-12-31", 187_300, 2025, "2026-02-11")]}
        },
        "NetIncomeLoss": {
            "units": {"USD": [_period("2025-01-01", "2025-12-31", -8_200, 2025, "2026-02-11")]}
        },
        "StockholdersEquity": {
            "units": {"USD": [_instant("2025-12-31", 36_000, 2025, "2026-02-11")]}
        },
    }


def test_weighted_average_shares_used_when_cover_page_count_is_stale():
    """Ford's last dei cover-page share count is dated 2011.

    Without this fallback there is no market cap, so no Z-Score, so the company
    is unscoreable on the head-to-head page entirely.
    """
    facts = {
        "facts": {
            "us-gaap": {
                **_minimal_statements(),
                "WeightedAverageNumberOfSharesOutstandingBasic": {
                    "units": {
                        "shares": [
                            _period("2025-01-01", "2025-12-31", 3_979_000_000, 2025, "2026-02-11")
                        ]
                    }
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {"end": "2011-04-28", "val": 3_727_332_952, "filed": "2011-05-10"}
                        ]
                    }
                }
            },
        }
    }

    with _provider(facts) as edgar:
        row = edgar.get_annual_financials("AAPL", years=1)[0]

    assert row.financials.shares_outstanding == pytest.approx(3_979_000_000)
    assert row.shares_source == "weighted_average"
    assert row.shares_are_approximate


def test_diluted_preferred_over_basic():
    facts = {
        "facts": {
            "us-gaap": {
                **_minimal_statements(),
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {
                        "shares": [
                            _period("2025-01-01", "2025-12-31", 4_010_000_000, 2025, "2026-02-11")
                        ]
                    }
                },
                "WeightedAverageNumberOfSharesOutstandingBasic": {
                    "units": {
                        "shares": [
                            _period("2025-01-01", "2025-12-31", 3_979_000_000, 2025, "2026-02-11")
                        ]
                    }
                },
            }
        }
    }

    with _provider(facts) as edgar:
        row = edgar.get_annual_financials("AAPL", years=1)[0]

    assert row.financials.shares_outstanding == pytest.approx(4_010_000_000)


def test_point_in_time_beats_weighted_average_when_both_present():
    facts = {
        "facts": {
            "us-gaap": {
                **_minimal_statements(),
                "WeightedAverageNumberOfSharesOutstandingBasic": {
                    "units": {
                        "shares": [
                            _period("2025-01-01", "2025-12-31", 3_979_000_000, 2025, "2026-02-11")
                        ]
                    }
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {"end": "2026-02-06", "val": 3_950_000_000, "filed": "2026-02-11"}
                        ]
                    }
                }
            },
        }
    }

    with _provider(facts) as edgar:
        row = edgar.get_annual_financials("AAPL", years=1)[0]

    assert row.financials.shares_outstanding == pytest.approx(3_950_000_000)
    assert row.shares_source == "point_in_time"


def test_no_share_count_at_all_reports_none():
    facts = {"facts": {"us-gaap": _minimal_statements()}}

    with _provider(facts) as edgar:
        row = edgar.get_annual_financials("AAPL", years=1)[0]

    assert row.financials.shares_outstanding is None
    assert row.shares_source is None
    assert not row.shares_are_approximate


# ---------------------------------------------------------------------- errors


def test_unknown_ticker_raises():
    with _provider(_facts()) as edgar:
        with pytest.raises(SymbolNotFound, match="ZZZZ"):
            edgar.get_annual_financials("ZZZZ")


def test_share_class_separator_is_normalized():
    """SEC writes BRK-B; quote vendors write BRK.B. Both must resolve.

    Without this, every dual-class company was reported as "not an SEC filer".
    """
    sec_map = {"0": {"cik_str": 1067983, "ticker": "BRK-B", "title": "Berkshire Hathaway"}}

    def handler(request):
        if "company_tickers" in request.url.path:
            return httpx.Response(200, json=sec_map)
        return httpx.Response(404)

    settings = _settings()
    client = httpx.Client(transport=httpx.MockTransport(handler), headers=settings.sec_headers)
    with EdgarProvider(settings=settings, client=client) as edgar:
        assert edgar.resolve_cik("BRK.B") == "0001067983"
        assert edgar.resolve_cik("BRK-B") == "0001067983"
        assert edgar.resolve_cik("brk.b") == "0001067983"

        with pytest.raises(SymbolNotFound):
            edgar.resolve_cik("BRK.C")


def test_dot_separator_map_resolves_hyphen_query():
    """The reverse direction too, in case the upstream format ever flips."""
    sec_map = {"0": {"cik_str": 14693, "ticker": "BF.B", "title": "Brown-Forman"}}

    def handler(request):
        if "company_tickers" in request.url.path:
            return httpx.Response(200, json=sec_map)
        return httpx.Response(404)

    settings = _settings()
    client = httpx.Client(transport=httpx.MockTransport(handler), headers=settings.sec_headers)
    with EdgarProvider(settings=settings, client=client) as edgar:
        assert edgar.resolve_cik("BF-B") == "0000014693"


def test_no_usable_period_raises():
    facts = _facts(Assets=[_instant("2024-12-31", 100_000, fy=2024, filed="2025-02-01")])

    with _provider(facts) as edgar:
        with pytest.raises(InsufficientData, match="total assets and revenue"):
            edgar.get_annual_financials("AAPL")


def test_403_explains_the_user_agent_requirement():
    def handler(request):
        if "company_tickers" in request.url.path:
            return httpx.Response(200, json=TICKER_MAP)
        return httpx.Response(403, text="Forbidden")

    settings = _settings()
    client = httpx.Client(transport=httpx.MockTransport(handler), headers=settings.sec_headers)
    with EdgarProvider(settings=settings, client=client) as edgar:
        with pytest.raises(ProviderError, match="SEC_USER_AGENT"):
            edgar.get_annual_financials("AAPL")


def test_years_must_be_positive():
    with _provider(_facts()) as edgar:
        with pytest.raises(ValueError, match="at least 1"):
            edgar.get_annual_financials("AAPL", years=0)


# ------------------------------------------------------------------ sic mapping


def test_profile_exposes_sic_and_variant():
    with _provider(_facts()) as edgar:
        profile = edgar.get_profile("AAPL")

    assert profile.cik == "0000320193"
    assert profile.sic == "3571"
    assert profile.z_variant == "public_manufacturer"
    assert not profile.is_financial


@pytest.mark.parametrize(
    "sic,expected",
    [
        (3571, "public_manufacturer"),   # electronic computers
        (2080, "public_manufacturer"),   # beverages
        ("3711", "public_manufacturer"), # motor vehicles
        (5331, "non_manufacturer"),      # retail
        (7372, "non_manufacturer"),      # prepackaged software
        (1311, "non_manufacturer"),      # crude petroleum
        (6021, None),                    # national commercial banks
        (6311, None),                    # life insurance
        (6798, None),                    # REITs
        (None, "non_manufacturer"),
        ("", "non_manufacturer"),
        ("not-a-number", "non_manufacturer"),
    ],
)
def test_z_variant_for_sic(sic, expected):
    assert z_variant_for_sic(sic) == expected
