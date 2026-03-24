from datetime import date

import requests

from flight_monitor.providers.base import PriceProvider


class KiwiPriceProvider(PriceProvider):
    name = "kiwi"

    def __init__(self, api_key: str, timeout_seconds: int = 15) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def get_roundtrip_price(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
        currency: str,
    ) -> float | None:
        endpoint = "https://api.tequila.kiwi.com/v2/search"
        headers = {"apikey": self._api_key}
        params = {
            "fly_from": origin,
            "fly_to": destination,
            "date_from": depart_date.strftime("%d/%m/%Y"),
            "date_to": depart_date.strftime("%d/%m/%Y"),
            "return_from": return_date.strftime("%d/%m/%Y"),
            "return_to": return_date.strftime("%d/%m/%Y"),
            "flight_type": "round",
            "curr": currency,
            "adults": 1,
            "sort": "price",
            "limit": 1,
        }

        try:
            response = requests.get(
                endpoint,
                headers=headers,
                params=params,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            print(
                "[WARN] Kiwi 查询失败 "
                f"{origin}->{destination} {depart_date}/{return_date}: {error}"
            )
            return None

        data = payload.get("data", [])
        if not data:
            return None

        best = data[0]
        price = best.get("price")
        if price is None:
            return None
        return float(price)
