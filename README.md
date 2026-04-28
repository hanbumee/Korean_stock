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

## Daily cron (local)

```
30 18 * * 1-5 /home/user/Korean_stock/scripts/cron_refresh.sh
```

Runs 18:30 KST Mon–Fri (after KRX close + EOD foreign-investor data publish). Logs to
`data/refresh.log`.

## Deploy to Streamlit Community Cloud (no laptop needed)

A GitHub Actions workflow at `.github/workflows/refresh.yml` runs `kstock.refresh`
daily on a schedule and commits the updated `data/kstock.db` back to this branch.
Streamlit Community Cloud auto-redeploys on each commit, so the dashboard URL is
always reading fresh data.

One-time setup (all from your phone browser):

1. **Trigger the first refresh** to populate the DB:
   - Open the repo on GitHub → **Actions** tab → "Refresh KRX foreign-ownership
     snapshots" → **Run workflow** → branch `claude/korean-stock-tracker-09X1u`.
   - Wait for the run to finish (≈ 5–15 min on first run; subsequent runs ≈ 1–2 min
     because ticker names are cached). Confirm a new commit landed with
     `data/kstock.db`.
2. **Deploy the dashboard**:
   - Go to <https://share.streamlit.io> and sign in with GitHub.
   - **New app** → repository `hanbumee/Korean_stock`, branch
     `claude/korean-stock-tracker-09X1u`, main file `app/dashboard.py`. Deploy.
   - You'll get a permanent URL like `https://<name>.streamlit.app`. Add to your
     iPhone home screen.
3. **Daily auto-refresh** is now on:
   - The cron runs at 09:30 UTC = 18:30 KST Mon–Fri.
   - Each successful refresh commits a new `data/kstock.db`; Streamlit Cloud
     redeploys within ~30 seconds.
   - You can also re-run the workflow on demand from the Actions tab.

Notes:

- pykrx scrapes `data.krx.co.kr` from a US-based GitHub-hosted runner. KRX is
  publicly accessible without an API key, but if a refresh fails, re-run the
  workflow manually — pykrx is occasionally flaky on transient KRX errors.
- The committed `data/kstock.db` is small (≈ a few MB even after months of
  history). If it ever grows large, prune older snapshots with a SQL `DELETE`.

## Tests

```bash
pytest tests/
```
