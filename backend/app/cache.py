"""Persistent cache for upstream market and filing data.

There is no user data here — no accounts, no saved portfolios, nothing personal.
Portfolios live in the browser's localStorage. This database exists purely so we
stop re-asking Alpaca and the SEC for figures that have not changed, which keeps
the app fast and keeps us well inside both providers' rate limits.

Freshness policy:
  * Price bars carry a TTL rather than being treated as immutable. Adjusted
    closes look immutable but are not — ``adjustment=all`` means a split
    retroactively rewrites a symbol's entire history, so a cache that never
    expired would serve pre-split prices indefinitely.
  * Filings genuinely are immutable once filed, but restatements and new annual
    reports arrive, so those get a longer TTL rather than none.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    String,
    Text,
    create_engine,
    delete,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

PRICE_TTL = timedelta(hours=6)
FILING_TTL = timedelta(hours=24)


class Base(DeclarativeBase):
    pass


class PriceBar(Base):
    __tablename__ = "price_bars"

    symbol: Mapped[str] = mapped_column(String(10), primary_key=True)
    bar_date: Mapped[date] = mapped_column(Date, primary_key=True)
    close: Mapped[float] = mapped_column(Float, nullable=False)


class PriceCoverage(Base):
    """What date range we have actually fetched for a symbol, and when."""

    __tablename__ = "price_coverage"

    symbol: Mapped[str] = mapped_column(String(10), primary_key=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    def covers(self, start: date, end: date) -> bool:
        return self.start_date <= start and self.end_date >= end

    def is_fresh(self, now: datetime, ttl: timedelta = PRICE_TTL) -> bool:
        return (now - self.fetched_at) < ttl


class FilingCache(Base):
    """Derived annual financials and profile, stored as JSON."""

    __tablename__ = "filing_cache"

    symbol: Mapped[str] = mapped_column(String(10), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    def is_fresh(self, now: datetime, ttl: timedelta = FILING_TTL) -> bool:
        return (now - self.fetched_at) < ttl


def make_engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, future=True)
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(url: str):
    return sessionmaker(bind=make_engine(url), expire_on_commit=False, future=True)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------- price API


def symbols_needing_fetch(
    session: Session,
    symbols: list[str],
    start: date,
    end: date,
    now: datetime | None = None,
) -> list[str]:
    """Which symbols lack fresh cached coverage for the whole requested window."""
    now = now or _now()
    rows = session.scalars(
        select(PriceCoverage).where(PriceCoverage.symbol.in_(symbols))
    ).all()
    covered = {
        row.symbol for row in rows if row.covers(start, end) and row.is_fresh(now)
    }
    return [s for s in symbols if s not in covered]


def store_prices(
    session: Session,
    closes: dict[str, dict[date, float]],
    start: date,
    end: date,
    now: datetime | None = None,
) -> None:
    """Replace cached bars for these symbols and record the coverage window."""
    now = now or _now()
    if not closes:
        return

    symbols = list(closes)
    session.execute(delete(PriceBar).where(PriceBar.symbol.in_(symbols)))
    session.execute(delete(PriceCoverage).where(PriceCoverage.symbol.in_(symbols)))

    session.add_all(
        [
            PriceBar(symbol=symbol, bar_date=bar_date, close=close)
            for symbol, series in closes.items()
            for bar_date, close in series.items()
        ]
    )
    session.add_all(
        [
            PriceCoverage(symbol=symbol, start_date=start, end_date=end, fetched_at=now)
            for symbol in symbols
        ]
    )
    session.commit()


def load_prices(
    session: Session,
    symbols: list[str],
    start: date,
    end: date,
) -> dict[str, dict[date, float]]:
    rows = session.scalars(
        select(PriceBar).where(
            PriceBar.symbol.in_(symbols),
            PriceBar.bar_date >= start,
            PriceBar.bar_date <= end,
        )
    ).all()

    out: dict[str, dict[date, float]] = {s: {} for s in symbols}
    for row in rows:
        out[row.symbol][row.bar_date] = row.close
    return out


# ------------------------------------------------------------------ filing API


def load_filing(
    session: Session,
    symbol: str,
    kind: str,
    now: datetime | None = None,
) -> dict | list | None:
    now = now or _now()
    row = session.get(FilingCache, (symbol, kind))
    if row is None or not row.is_fresh(now):
        return None
    return json.loads(row.payload)


def store_filing(
    session: Session,
    symbol: str,
    kind: str,
    payload: dict | list,
    now: datetime | None = None,
) -> None:
    now = now or _now()
    session.merge(
        FilingCache(
            symbol=symbol,
            kind=kind,
            payload=json.dumps(payload, default=str),
            fetched_at=now,
        )
    )
    session.commit()
