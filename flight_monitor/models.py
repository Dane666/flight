from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Route:
    origin: str
    destination: str


@dataclass(frozen=True)
class PriceQuote:
    route: Route
    depart_date: date
    return_date: date
    total_price: float
    currency: str
    provider: str
    observed_at: datetime
    depart_time: str | None = None
    arrive_time: str | None = None
    flight_number: str | None = None
    source_price: float | None = None
    source_currency: str | None = None
    exchange_rate: float | None = None
    price_position: str | None = None
