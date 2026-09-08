"""日期组合生成 — 根据窗口与行程约束生成去返日期对。"""

from datetime import date, timedelta


def _spans_both_weekend_days(start: date, end: date) -> bool:
    """闭区间 [start, end] 内是否同时包含周六与周日。"""
    if end < start:
        return False
    saw_sat = saw_sun = False
    cur = start
    while cur <= end:
        weekday = cur.weekday()  # 5=周六, 6=周日
        if weekday == 5:
            saw_sat = True
        elif weekday == 6:
            saw_sun = True
        if saw_sat and saw_sun:
            return True
        cur += timedelta(days=1)
    return saw_sat and saw_sun


def build_scan_pairs(
    scan_start: date,
    scan_end: date,
    min_trip_days: int = 4,
    max_trip_span_days: int | None = None,
    require_weekend: bool = False,
    max_return_date: date | None = None,
) -> list[tuple[date, date]]:
    """区间扫描：对 scan_start..scan_end 内每个出发日（出发日窗口），生成行程
    长度为 [min_trip_days, max_trip_span_days] 的去返日期对。

    - scan_start / scan_end 约束**出发日**范围（按月拆分时各自独立，无重叠）。
    - max_return_date 约束**返程日**上限，可晚于 scan_end，从而允许跨月行程
      （如 3/31 出发的 5 天行程回程溢出到 4 月初）而不把 4 月出发日纳入窗口。
    - 与 build_roundtrip_pairs 的窗口展开不同，本函数按出发日线性推进，
      复杂度 O(天数 × 行程跨度)，适合大区间（如跨数月）扫描，避免组合爆炸。
    """
    if scan_end < scan_start:
        raise ValueError("scan_end 必须不早于 scan_start")

    return_ceiling = max_return_date if max_return_date is not None else scan_end
    hi = max_trip_span_days if max_trip_span_days is not None else min_trip_days
    if hi < min_trip_days:
        hi = min_trip_days

    pairs: list[tuple[date, date]] = []
    cur = scan_start
    while cur <= scan_end:
        for span in range(min_trip_days, hi + 1):
            ret = cur + timedelta(days=span)
            if ret > return_ceiling:
                continue
            if require_weekend and not _spans_both_weekend_days(cur, ret):
                continue
            pairs.append((cur, ret))
        cur += timedelta(days=1)
    return pairs



def build_roundtrip_pairs(
    window_start: date,
    window_end: date,
    min_trip_days: int = 4,
    required_coverage_start: date | None = None,
    required_coverage_end: date | None = None,
    max_trip_span_days: int | None = None,
    max_leave_workdays: int | None = None,
) -> list[tuple[date, date]]:
    if window_end <= window_start:
        raise ValueError("window_end 必须晚于 window_start")

    def count_leave_workdays(
        depart_day: date,
        return_day: date,
    ) -> int:
        if required_coverage_start is None or required_coverage_end is None:
            return 0

        leave_days = 0
        current_day = depart_day
        while current_day <= return_day:
            in_holiday = (
                required_coverage_start <= current_day <= required_coverage_end
            )
            if current_day.weekday() < 5 and not in_holiday:
                leave_days += 1
            current_day += timedelta(days=1)
        return leave_days

    all_days: list[date] = []
    current = window_start
    while current <= window_end:
        all_days.append(current)
        current += timedelta(days=1)

    pairs: list[tuple[date, date]] = []
    for depart_day in all_days:
        for return_day in all_days:
            trip_days = (return_day - depart_day).days
            trip_span_days = trip_days + 1
            if trip_days < min_trip_days:
                continue
            if required_coverage_start and depart_day > required_coverage_start:
                continue
            if required_coverage_end and return_day < required_coverage_end:
                continue
            if (
                max_trip_span_days is not None
                and trip_span_days > max_trip_span_days
            ):
                continue
            if (
                max_leave_workdays is not None
                and count_leave_workdays(depart_day, return_day)
                > max_leave_workdays
            ):
                continue
            pairs.append((depart_day, return_day))
    return pairs
