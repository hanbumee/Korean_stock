"""Streamlit dashboard for Korean foreign-ownership flows.

Reads only from the SQLite cache populated by ``python -m kstock.refresh``.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# Make the project root importable when run via `streamlit run app/dashboard.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kstock import analysis, storage  # noqa: E402
from kstock.calendar import build_anchor_set, fmt  # noqa: E402
from kstock.config import (  # noqa: E402
    DEFAULT_CONSISTENCY_WINDOWS,
    MIN_FOREIGN_RATIO_PCT,
    MIN_MARKET_CAP_KRW,
    WINDOWS,
)

st.set_page_config(page_title="KRX Foreign Ownership Tracker", layout="wide")


@st.cache_data(ttl=300)
def _cached_dates() -> list[str]:
    return storage.list_snapshot_dates()


@st.cache_data(ttl=300)
def _cached_snapshot(date_str: str) -> pd.DataFrame:
    return storage.load_snapshot(date_str)


@st.cache_data(ttl=300)
def _cached_history(ticker: str) -> pd.DataFrame:
    return storage.load_ticker_history(ticker)


def _resolve_anchor_dates(t0_str: str, available: list[str]) -> dict[str, str]:
    """Map every window to the closest cached snapshot ≤ its calendar anchor."""
    t0 = datetime.strptime(t0_str, "%Y%m%d").date()
    aset = build_anchor_set(t0).anchors
    out: dict[str, str] = {}
    for window, target in aset.items():
        target_str = fmt(target)
        candidates = [d for d in available if d <= target_str]
        if candidates:
            out[window] = max(candidates)
    return out


def _format_table(df: pd.DataFrame) -> pd.DataFrame:
    """Tighten column display for st.dataframe."""
    if df.empty:
        return df
    out = df.copy()
    if "market_cap" in out.columns:
        out["market_cap (B KRW)"] = (out["market_cap"] / 1e9).round(1)
        out = out.drop(columns=["market_cap"])
    for c in out.columns:
        if c.startswith("d_") or c == "delta_ratio_pp" or c == "foreign_ratio":
            out[c] = out[c].astype(float).round(3)
    return out


def main() -> None:
    available_dates = _cached_dates()
    if not available_dates:
        st.title("Korean foreign-ownership tracker")
        st.warning(
            "No snapshots cached yet. Run `python -m kstock.refresh` first to populate "
            "`data/kstock.db`, then reload this page."
        )
        return

    t0_str = available_dates[-1]
    anchor_map = _resolve_anchor_dates(t0_str, available_dates)

    st.title("Korean foreign-ownership tracker")
    st.caption(
        f"Latest snapshot **{t0_str}** · cached dates: {len(available_dates)} · "
        f"resolved anchors: {', '.join(f'{w}={d}' for w, d in anchor_map.items())}"
    )

    with st.sidebar:
        st.header("Filters")
        market = st.selectbox("Market", ["ALL", "KOSPI", "KOSDAQ"], index=0)
        window = st.selectbox(
            "Window (per-window tab)",
            [w for w in WINDOWS if w in anchor_map],
            index=0,
        )
        min_cap_b = st.slider(
            "Min market cap (B KRW)", min_value=0, max_value=2000,
            value=int(MIN_MARKET_CAP_KRW / 1e9), step=10,
        )
        min_ratio = st.slider(
            "Min foreign ratio (%)", min_value=0.0, max_value=20.0,
            value=float(MIN_FOREIGN_RATIO_PCT), step=0.1,
        )
        top_n = st.slider("Top N per table", min_value=10, max_value=100, value=30, step=5)

        st.header("Consistency windows")
        selected_consistency = tuple(
            w for w in WINDOWS
            if w in anchor_map and st.checkbox(
                w, value=(w in DEFAULT_CONSISTENCY_WINDOWS), key=f"cw_{w}"
            )
        )

    min_cap = min_cap_b * 1_000_000_000
    market_arg = None if market == "ALL" else market

    t0_df = _cached_snapshot(t0_str)
    if t0_df.empty:
        st.error(f"Snapshot for {t0_str} is empty.")
        return

    tab_window, tab_consistency, tab_detail = st.tabs(
        ["Per-window rankings", "Consistent accumulators", "Per-ticker detail"]
    )

    with tab_window:
        anchor_str = anchor_map[window]
        anchor_df = _cached_snapshot(anchor_str)
        ranking = analysis.rank_window(
            t0_df, anchor_df, window, anchor_str,
            top_n=top_n, market=market_arg,
            min_market_cap=min_cap, min_foreign_ratio=min_ratio,
        )
        st.subheader(f"Window: {window} ({anchor_str} → {t0_str})")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### Top buyers (Δpp ↑)")
            st.dataframe(_format_table(ranking.top_buyers), use_container_width=True)
        with col2:
            st.markdown("### Top sellers (Δpp ↓)")
            st.dataframe(_format_table(ranking.top_sellers), use_container_width=True)

    with tab_consistency:
        if not selected_consistency:
            st.info("Select at least one window in the sidebar.")
        else:
            anchor_dfs = {w: _cached_snapshot(anchor_map[w]) for w in WINDOWS if w in anchor_map}
            flows = analysis.consistent_flows(
                t0_df, anchor_dfs,
                selected_windows=selected_consistency,
                market=market_arg,
                min_market_cap=min_cap, min_foreign_ratio=min_ratio,
            )
            st.subheader(
                f"Consistent across {', '.join(selected_consistency)} "
                f"({anchor_map[selected_consistency[-1]]} → {t0_str})"
            )
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### Continuous accumulators")
                st.caption("Foreign ratio rose in every selected window.")
                st.dataframe(
                    _format_table(flows["accumulators"].head(top_n)),
                    use_container_width=True,
                )
            with col2:
                st.markdown("### Continuous distributors")
                st.caption("Foreign ratio fell in every selected window.")
                st.dataframe(
                    _format_table(flows["distributors"].head(top_n)),
                    use_container_width=True,
                )

    with tab_detail:
        options = (
            t0_df[["ticker", "name", "market"]]
            .drop_duplicates()
            .sort_values("name")
        )
        labels = options["ticker"] + " — " + options["name"] + " (" + options["market"] + ")"
        choice = st.selectbox("Pick a ticker", labels.tolist())
        if choice:
            ticker = choice.split(" — ")[0]
            history = _cached_history(ticker)
            if history.empty:
                st.warning("No cached history for this ticker.")
            else:
                history = history.copy()
                history["date"] = pd.to_datetime(history["date"], format="%Y%m%d")
                history = history.set_index("date")
                st.subheader(f"{ticker} — foreign ratio over cached snapshots")
                st.line_chart(history["foreign_ratio"])

                # Δpp by window for this ticker.
                row = t0_df[t0_df["ticker"] == ticker]
                if not row.empty:
                    t0_ratio = float(row.iloc[0]["foreign_ratio"])
                    bars = []
                    for w in WINDOWS:
                        if w not in anchor_map:
                            continue
                        anchor_df = _cached_snapshot(anchor_map[w])
                        a = anchor_df[anchor_df["ticker"] == ticker]
                        if a.empty:
                            continue
                        bars.append({"window": w, "delta_pp": t0_ratio - float(a.iloc[0]["foreign_ratio"])})
                    if bars:
                        bar_df = pd.DataFrame(bars).set_index("window")
                        st.subheader("Δ foreign ratio by window")
                        st.bar_chart(bar_df["delta_pp"])


if __name__ == "__main__":
    main()
