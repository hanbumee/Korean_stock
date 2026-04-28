"""SQLite schema + idempotent upserts."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd

from .config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickers (
  ticker TEXT PRIMARY KEY,
  name   TEXT NOT NULL,
  market TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS foreign_snapshot (
  date           TEXT NOT NULL,
  ticker         TEXT NOT NULL,
  listed_shares  INTEGER,
  foreign_shares INTEGER,
  foreign_ratio  REAL,
  market_cap     INTEGER,
  PRIMARY KEY (date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_date ON foreign_snapshot(date);
"""


def init_db(path: Path = DB_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(_SCHEMA)


@contextmanager
def connect(path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    init_db(path)
    conn = sqlite3.connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_tickers(df: pd.DataFrame, path: Path = DB_PATH) -> None:
    if df.empty:
        return
    with connect(path) as conn:
        conn.executemany(
            "INSERT INTO tickers(ticker, name, market) VALUES (?, ?, ?) "
            "ON CONFLICT(ticker) DO UPDATE SET name=excluded.name, market=excluded.market",
            df[["ticker", "name", "market"]].itertuples(index=False, name=None),
        )


def has_snapshot(date_str: str, market: str, path: Path = DB_PATH) -> bool:
    """True iff snapshot rows exist for the given (date, market) pair."""
    with connect(path) as conn:
        cur = conn.execute(
            "SELECT 1 FROM foreign_snapshot s "
            "JOIN tickers t ON t.ticker = s.ticker "
            "WHERE s.date = ? AND t.market = ? LIMIT 1",
            (date_str, market),
        )
        return cur.fetchone() is not None


def upsert_snapshot(date_str: str, df: pd.DataFrame, path: Path = DB_PATH) -> None:
    if df.empty:
        return
    rows = [
        (
            date_str,
            row.ticker,
            int(row.listed_shares) if pd.notna(row.listed_shares) else None,
            int(row.foreign_shares) if pd.notna(row.foreign_shares) else None,
            float(row.foreign_ratio) if pd.notna(row.foreign_ratio) else None,
            int(row.market_cap) if pd.notna(row.market_cap) else None,
        )
        for row in df.itertuples(index=False)
    ]
    with connect(path) as conn:
        conn.executemany(
            "INSERT INTO foreign_snapshot"
            "(date, ticker, listed_shares, foreign_shares, foreign_ratio, market_cap) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(date, ticker) DO UPDATE SET "
            "  listed_shares=excluded.listed_shares,"
            "  foreign_shares=excluded.foreign_shares,"
            "  foreign_ratio=excluded.foreign_ratio,"
            "  market_cap=excluded.market_cap",
            rows,
        )


def load_snapshot(date_str: str, path: Path = DB_PATH) -> pd.DataFrame:
    """Return joined snapshot for one date, with name and market attached."""
    with connect(path) as conn:
        return pd.read_sql_query(
            "SELECT s.date, s.ticker, t.name, t.market, "
            "       s.listed_shares, s.foreign_shares, s.foreign_ratio, s.market_cap "
            "FROM foreign_snapshot s JOIN tickers t ON t.ticker = s.ticker "
            "WHERE s.date = ?",
            conn,
            params=(date_str,),
        )


def load_ticker_history(ticker: str, path: Path = DB_PATH) -> pd.DataFrame:
    """Return every cached snapshot for one ticker, ordered by date."""
    with connect(path) as conn:
        return pd.read_sql_query(
            "SELECT date, foreign_ratio, foreign_shares, market_cap "
            "FROM foreign_snapshot WHERE ticker = ? ORDER BY date",
            conn,
            params=(ticker,),
        )


def list_snapshot_dates(path: Path = DB_PATH) -> list[str]:
    with connect(path) as conn:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT date FROM foreign_snapshot ORDER BY date"
        )]
