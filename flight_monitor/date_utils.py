from datetime import date, timedelta

import holidays


def dragon_boat_date(year: int) -> date:
    cn_holidays = holidays.country_holidays("CN", years=year, language="en_US")
    for day, name in cn_holidays.items():
        if "Dragon Boat Festival" in str(name):
            return day
    return date(year, 6, 20)


def _single_day_holiday_span(festival_day: date) -> tuple[date, date]:
    """Extend a single-day holiday into a continuous Fri—Sun span."""
    start = festival_day
    end = festival_day

    while start.weekday() > 4:
        start -= timedelta(days=1)
    while end.weekday() < 5:
        next_day = end + timedelta(days=1)
        if next_day.weekday() >= 5:
            end = next_day
        else:
            break

    while (start - timedelta(days=1)).weekday() >= 5:
        start -= timedelta(days=1)
    while (end + timedelta(days=1)).weekday() >= 5:
        end += timedelta(days=1)

    return start, end


def dragon_boat_holiday_span(year: int) -> tuple[date, date]:
    festival_day = dragon_boat_date(year)
    return _single_day_holiday_span(festival_day)


def mid_autumn_date(year: int) -> date:
    cn_holidays = holidays.country_holidays("CN", years=year, language="en_US")
    for day, name in cn_holidays.items():
        if "Mid-Autumn Festival" in str(name):
            return day
    return date(year, 9, 25)


def mid_autumn_holiday_span(year: int) -> tuple[date, date]:
    festival_day = mid_autumn_date(year)
    return _single_day_holiday_span(festival_day)


def national_day_start(year: int) -> date:
    return date(year, 10, 1)


def national_day_holiday_span(year: int) -> tuple[date, date]:
    start = date(year, 10, 1)
    end = date(year, 10, 7)
    return start, end


def spring_festival_date(year: int) -> date:
    cn_holidays = holidays.country_holidays("CN", years=year, language="en_US")
    for day, name in cn_holidays.items():
        if "Spring Festival" in str(name):
            return day
    return date(year, 2, 17)


def spring_festival_holiday_span(year: int) -> tuple[date, date]:
    """Return the continuous public-holiday block for Spring Festival.

    Chinese New Year is typically 3 consecutive official public holidays.
    This function finds all consecutive public holidays around the Spring
    Festival date and extends to adjacent weekends.
    """
    cn_holidays = holidays.country_holidays("CN", years=year, language="en_US")
    holiday_dates: set[date] = set(cn_holidays.keys())

    festival_day = spring_festival_date(year)

    start = festival_day
    while (start - timedelta(days=1)) in holiday_dates:
        start -= timedelta(days=1)

    end = festival_day
    while (end + timedelta(days=1)) in holiday_dates:
        end += timedelta(days=1)

    # Extend to adjacent weekends
    while (start - timedelta(days=1)).weekday() >= 5:
        start -= timedelta(days=1)
    while (end + timedelta(days=1)).weekday() >= 5:
        end += timedelta(days=1)

    return start, end


def get_festival_span(festival: str, year: int) -> tuple[date, date]:
    registry = {
        "dragon_boat": dragon_boat_holiday_span,
        "mid_autumn": mid_autumn_holiday_span,
        "national_day": national_day_holiday_span,
        "spring_festival": spring_festival_holiday_span,
    }
    func = registry.get(festival)
    if func is None:
        raise ValueError(f"不支持的节日: {festival}")
    return func(year)


def around_day_window(center_day: date, days: int = 1) -> tuple[date, date]:
    return center_day - timedelta(days=days), center_day + timedelta(days=days)
