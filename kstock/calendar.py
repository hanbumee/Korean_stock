"""Anchor-date math for the time-horizon snapshots.

Calendar offsets (1m, 6m, 1y) use ``dateutil.relativedelta``. Business-day adjustment
is delegated to the data layer: callers receive a calendar target here and walk it back
to the nearest available KRX business day at fetch time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from .config import WINDOWS


def _step_back_business_days(d: date, n: int) -> date:
    """Step ``d`` back by ``n`` weekdays (Mon–Fri).

    This is a coarse business-day calculator that ignores KRX holidays; the data layer
    handles holiday gaps by walking back further when a fetch returns empty.
    """
    out = d
    steps = 0
    while steps < n:
        out -= timedelta(days=1)
        if out.weekday() < 5:
            steps += 1
    return out


def _previous_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def anchor_for_window(t0: date, window: str) -> date:
    """Return the (calendar) anchor date for a time window relative to ``t0``."""
    if window == "1d":
        return _step_back_business_days(t0, 1)
    if window == "2d":
        return _step_back_business_days(t0, 2)
    if window == "3d":
        return _step_back_business_days(t0, 3)
    if window == "1w":
        return _step_back_business_days(t0, 5)
    if window == "2w":
        return _step_back_business_days(t0, 10)
    if window == "1m":
        return _previous_weekday(t0 - relativedelta(months=1))
    if window == "6m":
        return _previous_weekday(t0 - relativedelta(months=6))
    if window == "1y":
        return _previous_weekday(t0 - relativedelta(years=1))
    raise ValueError(f"unknown window: {window!r}")


@dataclass(frozen=True)
class AnchorSet:
    t0: date
    anchors: dict[str, date]


def build_anchor_set(t0: date) -> AnchorSet:
    """Compute every anchor date for ``t0``."""
    return AnchorSet(t0=t0, anchors={w: anchor_for_window(t0, w) for w in WINDOWS})


def fmt(d: date) -> str:
    """KRX-style yyyymmdd string."""
    return d.strftime("%Y%m%d")
