from datetime import date

import requests

from flight_monitor.providers.base import PriceProvider


class AmadeusPriceProvider(PriceProvider):
    name = "amadeus"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str = "https://test.api.amadeus.com",
        timeout_seconds: int = 20,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._access_token: str | None = None

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        token_url = f"{self._base_url}/v1/security/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        response = requests.post(
            token_url,
            data=payload,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        token_data = response.json()
        token = token_data.get("access_token")
        if not token:
            raise ValueError("Amadeus token 响应缺少 access_token")
        self._access_token = token
        return token

    def get_roundtrip_price(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
        currency: str,
    ) -> float | None:
        try:
            token = self._get_access_token()
        except requests.RequestException as error:
            print(f"[WARN] Amadeus token 获取失败: {error}")
            return None

        endpoint = f"{self._base_url}/v2/shopping/flight-offers"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": depart_date.isoformat(),
            "returnDate": return_date.isoformat(),
            "adults": 1,
            "currencyCode": currency,
            "max": 10,
        }

        try:
            response = requests.get(
                endpoint,
                headers=headers,
                params=params,
                timeout=self._timeout_seconds,
            )
            if response.status_code == 401:
                self._access_token = None
                token = self._get_access_token()
                headers["Authorization"] = f"Bearer {token}"
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
                "[WARN] Amadeus 查询失败 "
                f"{origin}->{destination} {depart_date}/{return_date}: {error}"
            )
            return None

        offers = payload.get("data", [])
        if not offers:
            return None

        prices: list[float] = []
        for offer in offers:
            total = offer.get("price", {}).get("total")
            if total is None:
                continue
            try:
                prices.append(float(total))
            except (TypeError, ValueError):
                continue

        if not prices:
            return None
        return min(prices)
