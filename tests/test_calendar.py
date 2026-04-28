from datetime import date

from kstock.calendar import anchor_for_window, build_anchor_set, fmt
from kstock.config import WINDOWS


def test_business_day_offsets_skip_weekends():
    # Monday 2026-04-27. 1bd back -> Friday 2026-04-24.
    t0 = date(2026, 4, 27)
    assert anchor_for_window(t0, "1d") == date(2026, 4, 24)
    assert anchor_for_window(t0, "2d") == date(2026, 4, 23)
    # 1 week back from Mon = previous Mon (5 weekdays back).
    assert anchor_for_window(t0, "1w") == date(2026, 4, 20)
    # 2 weeks = 10 weekdays back.
    assert anchor_for_window(t0, "2w") == date(2026, 4, 13)


def test_business_day_offsets_from_friday():
    # Friday 2026-04-24. 1bd back -> Thursday 2026-04-23.
    t0 = date(2026, 4, 24)
    assert anchor_for_window(t0, "1d") == date(2026, 4, 23)
    # 3bd back -> Tuesday 2026-04-21.
    assert anchor_for_window(t0, "3d") == date(2026, 4, 21)


def test_calendar_offsets_land_on_weekday():
    t0 = date(2026, 4, 27)  # Monday
    # 1m back: 2026-03-27 (Friday) -> already a weekday.
    assert anchor_for_window(t0, "1m") == date(2026, 3, 27)
    # 6m back from 2026-04-27 is 2025-10-27 (Monday).
    assert anchor_for_window(t0, "6m") == date(2025, 10, 27)
    # 1y back from 2026-04-27 is 2025-04-27 — that's a Sunday.
    # _previous_weekday should walk to Friday 2025-04-25.
    assert anchor_for_window(t0, "1y") == date(2025, 4, 25)


def test_build_anchor_set_covers_every_window():
    t0 = date(2026, 4, 27)
    aset = build_anchor_set(t0)
    assert aset.t0 == t0
    assert set(aset.anchors.keys()) == set(WINDOWS)
    for d in aset.anchors.values():
        assert d < t0


def test_fmt():
    assert fmt(date(2026, 4, 27)) == "20260427"
