# Korean Stock Foreign-Ownership Tracker

Tracks foreign shareholding ratio (외국인 지분율) for every KOSPI and KOSDAQ stock at
multiple time horizons (1y / 6m / 1m / 2w / 1w / 3d / 2d / 1d) and ranks the biggest
foreign accumulators and distributors per window. A "consistent accumulators" view
surfaces names foreigners are buying across both short- and long-term windows.

Data source: [pykrx](https://github.com/sharebook-kr/pykrx) (KRX scraper).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Refresh data

```bash
python -m kstock.refresh
```

First run backfills snapshots for `t0` (latest KRX business day) and every anchor date
(1d, 2d, 3d, 1w, 2w, 1m, 6m, 1y ago) for both KOSPI and KOSDAQ into `data/kstock.db`.
Subsequent runs only fetch the new `t0` snapshot — existing rows are reused.

## Run the dashboard

```bash
streamlit run app/dashboard.py
```

Open <http://localhost:8501>.

Three tabs:

1. **Per-window rankings** — Top Buyers / Top Sellers for the chosen window.
2. **Consistent accumulators** — names with positive Δpp across every selected window
   (default: 1w, 1m, 6m, 1y).
3. **Per-ticker detail** — line chart of foreign ratio over all cached dates plus Δpp by
   window.

## Daily cron

```
30 18 * * 1-5 /home/user/Korean_stock/scripts/cron_refresh.sh
```

Runs 18:30 KST Mon–Fri (after KRX close + EOD foreign-investor data publish). Logs to
`data/refresh.log`.

## Tests

```bash
pytest tests/
```
