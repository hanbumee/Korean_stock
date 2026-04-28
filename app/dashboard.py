"""Streamlit dashboard for Korean foreign-ownership flows.

Reads only from the SQLite cache populated by ``python -m kstock.refresh``.
Stock prices for the per-ticker chart are fetched on demand via FinanceDataReader
(Naver Finance backend — no KRX login needed at view time).
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
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

VIEWS = (
    "Per-window rankings",
    "By foreign ratio",
    "Consistent accumulators",
    "Per-ticker detail",
)
DETAIL_IDX = VIEWS.index("Per-ticker detail")


@st.cache_data(ttl=300)
def _cached_dates() -> list[str]:
    return storage.list_snapshot_dates()


@st.cache_data(ttl=300)
def _cached_snapshot(date_str: str) -> pd.DataFrame:
    return storage.load_snapshot(date_str)


@st.cache_data(ttl=300)
def _cached_history(ticker: str) -> pd.DataFrame:
    return storage.load_ticker_history(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_prices(ticker: str, start: str) -> pd.DataFrame:
    """OHLCV via FinanceDataReader (Naver Finance). No KRX login required."""
    import FinanceDataReader as fdr
    return fdr.DataReader(ticker, start=start)


def _resolve_anchor_dates(t0_str: str, available: list[str]) -> dict[str, str]:
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


def _selectable_table(df: pd.DataFrame, key: str) -> None:
    """Render a dataframe with single-row selection. Clicking a row jumps to the
    detail view focused on that ticker."""
    display = _format_table(df)
    event = st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=key,
    )
    sel = getattr(event, "selection", None)
    rows = getattr(sel, "rows", None) if sel is not None else None
    if rows:
        idx = rows[0]
        if 0 <= idx < len(df):
            ticker = str(df.iloc[idx]["ticker"])
            if st.session_state.get("focus_ticker") != ticker or \
               st.session_state.get("active_view_idx") != DETAIL_IDX:
                st.session_state["focus_ticker"] = ticker
                st.session_state["active_view_idx"] = DETAIL_IDX
                st.rerun()


def _render_per_window(t0_df, t0_str, anchor_map, window, *, top_n,
                       market_arg, min_cap, min_ratio):
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
        _selectable_table(ranking.top_buyers, key=f"buyers_{window}")
    with col2:
        st.markdown("### Top sellers (Δpp ↓)")
        _selectable_table(ranking.top_sellers, key=f"sellers_{window}")


def _render_by_ratio(t0_df, t0_str, *, top_n, market_arg, min_cap, min_ratio):
    filtered = analysis.apply_filters(
        t0_df, market=market_arg,
        min_market_cap=min_cap, min_foreign_ratio=min_ratio,
    )
    sort_dir = st.radio(
        "Sort", ["Highest first", "Lowest first"], index=0,
        horizontal=True, key="by_ratio_sort",
    )
    ascending = sort_dir == "Lowest first"
    sorted_df = filtered.sort_values("foreign_ratio", ascending=ascending).head(top_n)
    cols = ["ticker", "name", "market", "foreign_ratio", "foreign_shares", "market_cap"]
    st.subheader(f"Stocks by foreign ownership ({t0_str})")
    st.caption(
        f"{len(filtered):,} of {len(t0_df):,} stocks match the current filters; "
        f"showing top {min(top_n, len(filtered)):,}."
    )
    _selectable_table(sorted_df[cols], key=f"by_ratio_{sort_dir}")


def _render_consistency(t0_df, t0_str, anchor_map, selected_consistency, *,
                        top_n, market_arg, min_cap, min_ratio):
    if not selected_consistency:
        st.info("Select at least one window in the sidebar.")
        return
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
        _selectable_table(flows["accumulators"].head(top_n), key="acc")
    with col2:
        st.markdown("### Continuous distributors")
        st.caption("Foreign ratio fell in every selected window.")
        _selectable_table(flows["distributors"].head(top_n), key="dist")


def _render_detail(t0_df, t0_str, anchor_map):
    options = (
        t0_df[["ticker", "name", "market"]]
        .drop_duplicates()
        .sort_values("name")
        .reset_index(drop=True)
    )
    labels = options["ticker"] + " — " + options["name"] + " (" + options["market"] + ")"
    label_list = labels.tolist()

    focus = st.session_state.get("focus_ticker")
    default_idx = 0
    if focus:
        match = options.index[options["ticker"] == focus].tolist()
        if match:
            default_idx = int(match[0])

    choice = st.selectbox("Pick a ticker", label_list, index=default_idx, key="detail_pick")
    if not choice:
        return
    ticker = choice.split(" — ")[0]
    name = options.loc[options["ticker"] == ticker, "name"].iloc[0]
    st.session_state["focus_ticker"] = ticker

    # Foreign ratio history (from cached snapshots).
    history = _cached_history(ticker)
    st.subheader(f"{ticker} {name} — foreign ratio over cached snapshots")
    if history.empty:
        st.info("No cached history for this ticker.")
    else:
        history = history.copy()
        history["date"] = pd.to_datetime(history["date"], format="%Y%m%d")
        st.line_chart(history.set_index("date")["foreign_ratio"])

    # Δpp by window.
    row = t0_df[t0_df["ticker"] == ticker]
    if not row.empty:
        t0_ratio = float(row.iloc[0]["foreign_ratio"])
        bars = []
        for w in WINDOWS:
            if w not in anchor_map:
                continue
            anchor_df = _cached_snapshot(anchor_map[w])
            a = anchor_df[anchor_df["ticker"] == ticker]
            if not a.empty:
                bars.append({"window": w, "delta_pp": t0_ratio - float(a.iloc[0]["foreign_ratio"])})
        if bars:
            st.subheader("Δ foreign ratio by window")
            st.bar_chart(pd.DataFrame(bars).set_index("window")["delta_pp"])

    # Stock price chart (FinanceDataReader, Naver backend).
    st.subheader(f"{ticker} {name} — close price")
    range_choice = st.radio(
        "Range", ["1m", "3m", "6m", "1y", "3y"], index=3, horizontal=True,
        key="price_range",
    )
    days = {"1m": 30, "3m": 92, "6m": 183, "1y": 365, "3y": 365 * 3}[range_choice]
    start = (datetime.strptime(t0_str, "%Y%m%d") - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        with st.spinner("Fetching prices…"):
            prices = _cached_prices(ticker, start)
    except Exception as exc:
        st.error(f"Could not load prices: {exc}")
    else:
        if prices is None or prices.empty or "Close" not in prices.columns:
            st.info("No price data available.")
        else:
            st.line_chart(prices["Close"])


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
            "Window (per-window view)",
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
        top_n = st.slider("Top N per table", min_value=10, max_value=200, value=50, step=10)

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

    # Programmatic navigation: row-click handlers set active_view_idx then rerun.
    # The radio reads its default index from session state on each rerun.
    if "active_view_idx" not in st.session_state:
        st.session_state["active_view_idx"] = 0
    active = st.radio(
        "View", VIEWS, horizontal=True,
        index=st.session_state["active_view_idx"],
        label_visibility="collapsed",
    )
    st.session_state["active_view_idx"] = VIEWS.index(active)

    if active == "Per-window rankings":
        _render_per_window(
            t0_df, t0_str, anchor_map, window,
            top_n=top_n, market_arg=market_arg,
            min_cap=min_cap, min_ratio=min_ratio,
        )
    elif active == "By foreign ratio":
        _render_by_ratio(
            t0_df, t0_str,
            top_n=top_n, market_arg=market_arg,
            min_cap=min_cap, min_ratio=min_ratio,
        )
    elif active == "Consistent accumulators":
        _render_consistency(
            t0_df, t0_str, anchor_map, selected_consistency,
            top_n=top_n, market_arg=market_arg,
            min_cap=min_cap, min_ratio=min_ratio,
        )
    else:
        _render_detail(t0_df, t0_str, anchor_map)


if __name__ == "__main__":
    main()
