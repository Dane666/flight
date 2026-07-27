from datetime import date

import pytest

from flight_monitor.scheduling import build_roundtrip_pairs


def test_basic_window_generates_pairs():
    pairs = build_roundtrip_pairs(
        date(2026, 6, 17), date(2026, 6, 19), min_trip_days=1
    )
    # 3 days => C(3,2) = 3 ordered pairs with depart < return and trip_days >= 1
    assert len(pairs) == 3
    assert all(d < r for d, r in pairs)


def test_min_trip_days_filter():
    pairs = build_roundtrip_pairs(
        date(2026, 6, 17), date(2026, 6, 22), min_trip_days=4
    )
    assert all((r - d).days >= 4 for d, r in pairs)


def test_max_trip_span_days_filter():
    pairs = build_roundtrip_pairs(
        date(2026, 6, 17),
        date(2026, 6, 30),
        min_trip_days=1,
        max_trip_span_days=3,
    )
    assert all((r - d).days + 1 <= 3 for d, r in pairs)


def test_required_coverage_window():
    pairs = build_roundtrip_pairs(
        date(2026, 6, 17),
        date(2026, 6, 30),
        min_trip_days=1,
        required_coverage_start=date(2026, 6, 19),
        required_coverage_end=date(2026, 6, 21),
    )
    assert all(d <= date(2026, 6, 19) for d, _ in pairs)
    assert all(r >= date(2026, 6, 21) for _, r in pairs)


def test_max_leave_workdays_filter():
    # 周一 2026-06-22 ~ 周日 2026-06-28，要求覆盖 6/24~6/26 (周中假期)
    pairs = build_roundtrip_pairs(
        date(2026, 6, 22),
        date(2026, 6, 28),
        min_trip_days=1,
        required_coverage_start=date(2026, 6, 24),
        required_coverage_end=date(2026, 6, 26),
        max_leave_workdays=1,
    )
    # 若返程落在周六之后，请假天数应 <= 1
    for d, r in pairs:
        leave = sum(
            1
            for i in range((r - d).days + 1)
            if (d + __import__("datetime").timedelta(days=i)).weekday() < 5
            and not (date(2026, 6, 24) <= d + __import__("datetime").timedelta(days=i) <= date(2026, 6, 26))
        )
        assert leave <= 1


def test_invalid_window_raises():
    with pytest.raises(ValueError):
        build_roundtrip_pairs(date(2026, 6, 20), date(2026, 6, 19))
