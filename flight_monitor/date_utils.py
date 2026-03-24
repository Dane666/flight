from datetime import date, timedelta

import holidays


def dragon_boat_date(year: int) -> date:
    cn_holidays = holidays.country_holidays("CN", years=year, language="en_US")
    for day, name in cn_holidays.items():
        if "Dragon Boat Festival" in str(name):
            return day
    return date(year, 6, 20)


def around_day_window(center_day: date, days: int = 1) -> tuple[date, date]:
    return center_day - timedelta(days=days), center_day + timedelta(days=days)
