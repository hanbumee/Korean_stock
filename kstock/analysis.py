"""Pure pandas operations: deltas, per-window rankings, multi-window consistency.

All functions take pre-loaded DataFrames so they're trivially unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import (
    DEFAULT_CONSISTENCY_WINDOWS,
    MIN_FOREIGN_RATIO_PCT,
    MIN_MARKET_CAP_KRW,
    WINDOWS,
)


def is_preferred_share(ticker: str) -> bool:
    """KRX preferred shares end in a non-zero digit (e.g. 005935 vs. common 005930)."""
    return bool(ticker) and ticker[-1] != "0"


def is_spac(name: str) -> bool:
    return isinstance(name, str) and "스팩" in name


def apply_filters(
    df: pd.DataFrame,
    *,
    market: str | None = None,
    min_market_cap: float = MIN_MARKET_CAP_KRW,
    min_foreign_ratio: float = MIN_FOREIGN_RATIO_PCT,
) -> pd.DataFrame:
    """Apply liquidity / sanity filters before ranking. Operates on a t0-snapshot DataFrame
    (one row per ticker)."""
    out = df.copy()
    if market and market != "ALL":
        out = out[out["market"] == market]
    out = out[~out["ticker"].map(is_preferred_share)]
    out = out[~out["name"].map(is_spac)]
    out = out[out["market_cap"].fillna(0) >= min_market_cap]
    out = out[out["foreign_ratio"].fillna(0) >= min_foreign_ratio]
    return out.reset_index(drop=True)


def compute_deltas(t0_df: pd.DataFrame, anchor_df: pd.DataFrame) -> pd.DataFrame:
    """Inner-join t0 and anchor snapshots; return a frame with delta columns."""
    merged = t0_df.merge(
        anchor_df[["ticker", "foreign_ratio", "foreign_shares"]].rename(
            columns={
                "foreign_ratio": "foreign_ratio_anchor",
                "foreign_shares": "foreign_shares_anchor",
            }
        ),
        on="ticker",
        how="inner",
    )
    merged["delta_ratio_pp"] = merged["foreign_ratio"] - merged["foreign_ratio_anchor"]
    merged["delta_shares"] = merged["foreign_shares"] - merged["foreign_shares_anchor"]
    return merged


@dataclass
class WindowRanking:
    window: str
    anchor_date: str
    top_buyers: pd.DataFrame
    top_sellers: pd.DataFrame


def rank_window(
    t0_df: pd.DataFrame,
    anchor_df: pd.DataFrame,
    window: str,
    anchor_date: str,
    *,
    top_n: int = 30,
    market: str | None = None,
    min_market_cap: float = MIN_MARKET_CAP_KRW,
    min_foreign_ratio: float = MIN_FOREIGN_RATIO_PCT,
) -> WindowRanking:
    filtered = apply_filters(
        t0_df,
        market=market,
        min_market_cap=min_market_cap,
        min_foreign_ratio=min_foreign_ratio,
    )
    deltas = compute_deltas(filtered, anchor_df)

    cols = [
        "ticker", "name", "market", "foreign_ratio", "delta_ratio_pp",
        "delta_shares", "market_cap",
    ]
    buyers = deltas.sort_values("delta_ratio_pp", ascending=False).head(top_n)[cols]
    sellers = deltas.sort_values("delta_ratio_pp", ascending=True).head(top_n)[cols]
    return WindowRanking(
        window=window,
        anchor_date=anchor_date,
        top_buyers=buyers.reset_index(drop=True),
        top_sellers=sellers.reset_index(drop=True),
    )


def consistent_flows(
    t0_df: pd.DataFrame,
    anchor_dfs: dict[str, pd.DataFrame],
    *,
    selected_windows: tuple[str, ...] = DEFAULT_CONSISTENCY_WINDOWS,
    market: str | None = None,
    min_market_cap: float = MIN_MARKET_CAP_KRW,
    min_foreign_ratio: float = MIN_FOREIGN_RATIO_PCT,
) -> dict[str, pd.DataFrame]:
    """Return {'accumulators', 'distributors'}: tickers whose Δpp is positive (resp.
    negative) across every selected window.

    Adds a ``consistency_score`` (sum of sign(Δpp) across the selected windows) and a
    ``monotonic`` flag (Δpp magnitude grows with window length, no sub-window reversal).
    """
    base = apply_filters(
        t0_df,
        market=market,
        min_market_cap=min_market_cap,
        min_foreign_ratio=min_foreign_ratio,
    )

    delta_cols: list[str] = []
    out = base[["ticker", "name", "market", "foreign_ratio", "market_cap"]].copy()
    for w in WINDOWS:
        anchor_df = anchor_dfs.get(w)
        if anchor_df is None or anchor_df.empty:
            continue
        col = f"d_{w}"
        delta_cols.append(col)
        anchor_subset = anchor_df[["ticker", "foreign_ratio"]].rename(
            columns={"foreign_ratio": "_anchor_ratio"}
        )
        merged = out.merge(anchor_subset, on="ticker", how="left")
        out[col] = merged["foreign_ratio"] - merged["_anchor_ratio"]

    selected_cols = [f"d_{w}" for w in selected_windows if f"d_{w}" in out.columns]
    if not selected_cols:
        empty = out.iloc[0:0]
        return {"accumulators": empty, "distributors": empty}

    selected_arr = out[selected_cols].to_numpy()
    out["consistency_score"] = np.sign(selected_arr).sum(axis=1)

    # Monotonicity check across the (selected) windows ordered shortest -> longest:
    # accumulators: |Δpp| should be non-decreasing as horizon lengthens AND every Δpp > 0.
    # distributors: same shape with Δpp < 0.
    abs_arr = np.abs(selected_arr)
    monotonic_growth = np.all(np.diff(abs_arr, axis=1) >= 0, axis=1) if abs_arr.shape[1] > 1 else \
        np.ones(abs_arr.shape[0], dtype=bool)
    all_positive = np.all(selected_arr > 0, axis=1)
    all_negative = np.all(selected_arr < 0, axis=1)
    out["monotonic_up"] = all_positive & monotonic_growth
    out["monotonic_down"] = all_negative & monotonic_growth

    # Sort key for ties: prefer the longest available window's Δpp magnitude.
    longest = selected_cols[-1]

    accumulators = out[all_positive].copy()
    accumulators["monotonic"] = accumulators["monotonic_up"]
    accumulators = accumulators.drop(columns=["monotonic_up", "monotonic_down"])
    accumulators = accumulators.sort_values(
        ["consistency_score", longest], ascending=[False, False]
    ).reset_index(drop=True)

    distributors = out[all_negative].copy()
    distributors["monotonic"] = distributors["monotonic_down"]
    distributors = distributors.drop(columns=["monotonic_up", "monotonic_down"])
    distributors = distributors.sort_values(
        ["consistency_score", longest], ascending=[True, True]
    ).reset_index(drop=True)

    keep = (
        ["ticker", "name", "market", "foreign_ratio", "market_cap"]
        + delta_cols
        + ["consistency_score", "monotonic"]
    )
    return {
        "accumulators": accumulators[keep],
        "distributors": distributors[keep],
    }
