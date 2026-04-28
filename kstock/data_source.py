"""Thin wrappers over pykrx — the only module that touches the network."""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import pandas as pd
from pykrx import stock

from .calendar import fmt

log = logging.getLogger(__name__)

# How many calendar days to walk back when a target date returns no data
# (covers KRX holidays / market closures).
_BUSDAY_LOOKBACK = 7

# Light retry around transient KRX scraper hiccups.
_RETRIES = 3
_BACKOFF_SEC = 2.0


def _retry(fn, *args, **kwargs):
    last_exc: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # pykrx raises bare Exceptions on scrape failures
            last_exc = exc
            sleep = _BACKOFF_SEC * (2 ** attempt)
            log.warning("pykrx call failed (attempt %d): %s; sleeping %.1fs",
                        attempt + 1, exc, sleep)
            time.sleep(sleep)
    assert last_exc is not None
    raise last_exc


def latest_business_day(today: date | None = None) -> date:
    """Walk back from ``today`` (default: today) until pykrx returns a non-empty
    KOSPI ticker list — that's the most recent KRX business day with published data."""
    cursor = today or date.today()
    for _ in range(_BUSDAY_LOOKBACK + 1):
        tickers = _retry(stock.get_market_ticker_list, fmt(cursor), market="KOSPI")
        if tickers:
            return cursor
        cursor -= timedelta(days=1)
    raise RuntimeError("Could not find a recent KRX business day within lookback window")


def resolve_business_day(target: date) -> date:
    """Return the closest KRX business day on or before ``target``."""
    cursor = target
    for _ in range(_BUSDAY_LOOKBACK + 1):
        tickers = _retry(stock.get_market_ticker_list, fmt(cursor), market="KOSPI")
        if tickers:
            return cursor
        cursor -= timedelta(days=1)
    raise RuntimeError(f"No KRX business day found within {_BUSDAY_LOOKBACK} days of {target}")


def fetch_ticker_universe(d: date) -> pd.DataFrame:
    """Return a DataFrame of every KOSPI + KOSDAQ ticker active on ``d``.

    Columns: ticker, name, market.
    """
    rows = []
    for market in ("KOSPI", "KOSDAQ"):
        tickers = _retry(stock.get_market_ticker_list, fmt(d), market=market)
        for t in tickers:
            name = _retry(stock.get_market_ticker_name, t)
            rows.append({"ticker": t, "name": name, "market": market})
    return pd.DataFrame(rows)


def fetch_snapshot(d: date, market: str) -> pd.DataFrame:
    """Fetch a per-ticker foreign-ownership snapshot for ``d`` and ``market``.

    Joins ``get_exhaustion_rates_of_foreign_investment`` (foreign ratio) with
    ``get_market_cap`` (시가총액) so the storage layer can apply the market-cap floor
    without re-scraping.

    Returns columns: ticker, listed_shares, foreign_shares, foreign_ratio, market_cap.
    """
    foreign = _retry(stock.get_exhaustion_rates_of_foreign_investment, fmt(d), market)
    if foreign is None or foreign.empty:
        return pd.DataFrame(
            columns=["ticker", "listed_shares", "foreign_shares",
                     "foreign_ratio", "market_cap"]
        )

    foreign = foreign.rename(
        columns={
            "상장주식수": "listed_shares",
            "보유수량": "foreign_shares",
            "지분율": "foreign_ratio",
        }
    )[["listed_shares", "foreign_shares", "foreign_ratio"]]
    foreign.index.name = "ticker"

    cap = _retry(stock.get_market_cap, fmt(d), market=market)
    if cap is None or cap.empty:
        foreign["market_cap"] = pd.NA
    else:
        cap = cap.rename(columns={"시가총액": "market_cap"})[["market_cap"]]
        cap.index.name = "ticker"
        foreign = foreign.join(cap, how="left")

    out = foreign.reset_index()
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    return out
