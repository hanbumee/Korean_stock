"""CLI orchestrator: ensure today's t0 snapshot + every anchor snapshot exist on disk."""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime

from . import data_source, storage
from .calendar import build_anchor_set, fmt
from .config import MARKETS

log = logging.getLogger("kstock.refresh")


def _ensure_snapshot(target: date, *, force: bool = False) -> str:
    """Resolve ``target`` to the closest KRX business day, fetch any missing per-market
    snapshots, and persist them. Returns the resolved yyyymmdd string."""
    resolved = data_source.resolve_business_day(target)
    resolved_str = fmt(resolved)

    for market in MARKETS:
        if not force and storage.has_snapshot(resolved_str, market):
            log.info("snapshot %s/%s already cached, skipping", resolved_str, market)
            continue
        log.info("fetching snapshot %s/%s", resolved_str, market)
        df = data_source.fetch_snapshot(resolved, market)
        if df.empty:
            log.warning("empty snapshot for %s/%s", resolved_str, market)
            continue
        storage.upsert_snapshot(resolved_str, df)
    return resolved_str


def refresh(today: date | None = None, *, force: bool = False) -> dict[str, str]:
    """Refresh t0 + every anchor snapshot.

    Returns a mapping of window -> resolved yyyymmdd anchor date (plus 't0').
    """
    storage.init_db()
    t0 = data_source.latest_business_day(today)
    log.info("latest KRX business day: %s", fmt(t0))

    log.info("refreshing ticker universe from %s", fmt(t0))
    storage.upsert_tickers(data_source.fetch_ticker_universe(t0))

    resolved: dict[str, str] = {"t0": _ensure_snapshot(t0, force=force)}
    anchors = build_anchor_set(t0).anchors
    for window, anchor_date in anchors.items():
        resolved[window] = _ensure_snapshot(anchor_date, force=force)

    log.info("refresh complete: %s", resolved)
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh KRX foreign-ownership snapshots.")
    parser.add_argument("--today", help="Override 'today' as yyyymmdd (for testing).")
    parser.add_argument(
        "--force", action="store_true",
        help="Re-fetch snapshots even if already cached.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    today = datetime.strptime(args.today, "%Y%m%d").date() if args.today else None
    refresh(today=today, force=args.force)


if __name__ == "__main__":
    main()
