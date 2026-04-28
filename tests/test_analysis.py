import pandas as pd

from kstock.analysis import (
    apply_filters,
    compute_deltas,
    consistent_flows,
    is_preferred_share,
    is_spac,
    rank_window,
)


def _t0_frame():
    return pd.DataFrame([
        # Common stocks above floor
        {"ticker": "005930", "name": "삼성전자",   "market": "KOSPI",  "foreign_ratio": 52.0, "foreign_shares": 3_000_000_000, "market_cap": 500_000_000_000_000},
        {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI",  "foreign_ratio": 55.0, "foreign_shares": 400_000_000,   "market_cap": 200_000_000_000_000},
        {"ticker": "035420", "name": "NAVER",     "market": "KOSPI",  "foreign_ratio": 45.0, "foreign_shares": 70_000_000,    "market_cap": 30_000_000_000_000},
        # Filtered: preferred share
        {"ticker": "005935", "name": "삼성전자우", "market": "KOSPI",  "foreign_ratio": 80.0, "foreign_shares": 100_000_000,   "market_cap": 50_000_000_000_000},
        # Filtered: SPAC
        {"ticker": "123450", "name": "엔에이치스팩99호", "market": "KOSDAQ", "foreign_ratio": 5.0, "foreign_shares": 100_000, "market_cap": 200_000_000_000},
        # Filtered: market cap below floor (50B)
        {"ticker": "111110", "name": "작은회사",   "market": "KOSDAQ", "foreign_ratio": 30.0, "foreign_shares": 1_000_000,     "market_cap": 50_000_000_000},
        # Filtered: foreign ratio below floor (0.1%)
        {"ticker": "222220", "name": "외국인없음", "market": "KOSPI",  "foreign_ratio": 0.1,  "foreign_shares": 1_000,          "market_cap": 500_000_000_000},
    ])


def _anchor_frame(deltas: dict[str, float]):
    """Build an anchor frame where t0 ratios are shifted down by ``deltas`` per ticker."""
    rows = []
    for r in _t0_frame().itertuples():
        d = deltas.get(r.ticker, 0.0)
        rows.append({
            "ticker": r.ticker,
            "foreign_ratio": r.foreign_ratio - d,  # so t0 - anchor = d
            "foreign_shares": r.foreign_shares - int(d * 1_000_000),
        })
    return pd.DataFrame(rows)


def test_is_preferred_share():
    assert is_preferred_share("005935")
    assert not is_preferred_share("005930")


def test_is_spac():
    assert is_spac("엔에이치스팩99호")
    assert not is_spac("삼성전자")


def test_apply_filters_drops_preferred_spac_and_floors():
    out = apply_filters(_t0_frame())
    tickers = set(out["ticker"])
    assert "005935" not in tickers   # preferred
    assert "123450" not in tickers   # SPAC
    assert "111110" not in tickers   # tiny cap
    assert "222220" not in tickers   # foreign ratio below floor
    assert tickers == {"005930", "000660", "035420"}


def test_compute_deltas_signs():
    t0 = apply_filters(_t0_frame())
    anchor = _anchor_frame({"005930": 1.5, "000660": -2.0, "035420": 0.0})
    out = compute_deltas(t0, anchor).set_index("ticker")
    assert out.loc["005930", "delta_ratio_pp"] == 1.5
    assert out.loc["000660", "delta_ratio_pp"] == -2.0
    assert out.loc["035420", "delta_ratio_pp"] == 0.0


def test_rank_window_top_buyers_and_sellers():
    anchor = _anchor_frame({"005930": 1.5, "000660": -2.0, "035420": 0.5})
    rk = rank_window(_t0_frame(), anchor, "1w", "20260420", top_n=3)
    assert rk.top_buyers.iloc[0]["ticker"] == "005930"
    assert rk.top_sellers.iloc[0]["ticker"] == "000660"


def test_consistent_flows_identifies_continuous_accumulator():
    # Samsung up across all windows; SK Hynix down across all; NAVER mixed.
    anchor_dfs = {
        "1d": _anchor_frame({"005930": 0.1, "000660": -0.1, "035420": 0.2}),
        "3d": _anchor_frame({"005930": 0.3, "000660": -0.3, "035420": -0.1}),
        "1w": _anchor_frame({"005930": 0.5, "000660": -0.5, "035420": 0.3}),
        "2w": _anchor_frame({"005930": 0.8, "000660": -0.8, "035420": 0.4}),
        "1m": _anchor_frame({"005930": 1.2, "000660": -1.0, "035420": -0.2}),
        "6m": _anchor_frame({"005930": 3.0, "000660": -2.5, "035420": 1.0}),
        "1y": _anchor_frame({"005930": 5.0, "000660": -4.0, "035420": 2.0}),
    }
    # Need 2d entry too for completeness (analysis iterates all WINDOWS).
    anchor_dfs["2d"] = _anchor_frame({"005930": 0.2, "000660": -0.2, "035420": 0.0})

    flows = consistent_flows(
        _t0_frame(), anchor_dfs, selected_windows=("1w", "1m", "6m", "1y"),
    )
    accs = flows["accumulators"].set_index("ticker")
    dists = flows["distributors"].set_index("ticker")

    assert "005930" in accs.index, "Samsung should be a continuous accumulator"
    assert accs.loc["005930", "monotonic"]   # magnitudes grow with horizon
    assert accs.loc["005930", "consistency_score"] == 4

    assert "000660" in dists.index, "SK Hynix should be a continuous distributor"
    assert dists.loc["000660", "monotonic"]
    assert dists.loc["000660", "consistency_score"] == -4

    # NAVER is positive at 1w, negative at 1m -> not in either bucket.
    assert "035420" not in accs.index
    assert "035420" not in dists.index
