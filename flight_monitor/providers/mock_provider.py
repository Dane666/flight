import hashlib
from datetime import date

from flight_monitor.providers.base import PriceProvider


class MockPriceProvider(PriceProvider):
    name = "mock"

    base_price = {
        "CAN": 1500,
        "SZX": 1450,
        "HKG": 1700,
    }

    def get_roundtrip_price(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
        currency: str,
    ) -> float:
        route_base = self.base_price.get(origin.upper(), 1600)
        token = (
            f"{origin}-{destination}-{depart_date.isoformat()}-"
            f"{return_date.isoformat()}-{currency}"
        )
        seed = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16)
        jitter = seed % 900
        trip_length_factor = max((return_date - depart_date).days, 1) * 25
        return round(route_base + jitter + trip_length_factor, 2)
