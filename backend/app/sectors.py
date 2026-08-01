"""Sector classification derived from SEC SIC codes.

This is SIC divisions, not GICS. It is coarser than what a paid data vendor
supplies — "Manufacturing" covers both Coca-Cola and Nvidia — but it is free,
official, comes attached to data already being fetched, and is never wrong about
what it does say. Anything shown to a user should be labelled as SIC-derived so
it is not mistaken for GICS sectors.
"""

from __future__ import annotations

# SIC divisions as published by the SEC, in ascending order of range start.
_DIVISIONS: tuple[tuple[int, int, str], ...] = (
    (100, 999, "Agriculture & Forestry"),
    (1000, 1499, "Mining & Extraction"),
    (1500, 1799, "Construction"),
    (2000, 3999, "Manufacturing"),
    (4000, 4999, "Transportation & Utilities"),
    (5000, 5199, "Wholesale Trade"),
    (5200, 5999, "Retail Trade"),
    (6000, 6799, "Finance & Real Estate"),
    (7000, 8999, "Services"),
    (9100, 9729, "Public Administration"),
)

UNKNOWN = "Unclassified"
FUND = "Funds & ETFs"

# Major-group refinements within Manufacturing and Services, where the raw
# division is too broad to be informative for a portfolio view.
_MAJOR_GROUPS: dict[int, str] = {
    20: "Food & Beverage",
    28: "Pharma & Chemicals",
    35: "Technology Hardware",
    36: "Electronics & Semis",
    37: "Transportation Equipment",
    38: "Instruments & Medical Devices",
    48: "Communications",
    49: "Utilities",
    60: "Banking",
    63: "Insurance",
    65: "Real Estate",
    67: "Investment Offices",
    73: "Software & IT Services",
    80: "Health Services",
}


def sector_for_sic(sic: int | str | None) -> str:
    """Map a SIC code to a display sector.

    Falls back to the SIC division when no finer major-group label applies, and
    to ``Unclassified`` when the code is missing or unparseable.
    """
    if sic is None or sic == "":
        return UNKNOWN
    try:
        code = int(sic)
    except (TypeError, ValueError):
        return UNKNOWN

    major = code // 100
    refined = _MAJOR_GROUPS.get(major)
    if refined:
        return refined

    for low, high, name in _DIVISIONS:
        if low <= code <= high:
            return name

    return UNKNOWN
