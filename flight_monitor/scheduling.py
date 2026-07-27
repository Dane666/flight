"""日期组合生成 — 根据窗口与行程约束生成去返日期对。"""

from datetime import date, timedelta


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
