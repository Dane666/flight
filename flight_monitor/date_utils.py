from datetime import date, timedelta

import holidays


def dragon_boat_date(year: int) -> date:
    cn_holidays = holidays.country_holidays("CN", years=year, language="en_US")
    for day, name in cn_holidays.items():
        if "Dragon Boat Festival" in str(name):
            return day
    return date(year, 6, 20)


def dragon_boat_holiday_span(year: int) -> tuple[date, date]:
    festival_day = dragon_boat_date(year)
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


def around_day_window(center_day: date, days: int = 1) -> tuple[date, date]:
    return center_day - timedelta(days=days), center_day + timedelta(days=days)
