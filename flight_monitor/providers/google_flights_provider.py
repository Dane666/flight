from datetime import date, datetime

import requests

from flight_monitor.providers.base import PriceProvider


class GoogleFlightsPriceProvider(PriceProvider):
    name = "google_flights"
    quote_currency: str | None = None

    def __init__(
        self,
        api_key: str,
        hl: str = "en",
        gl: str = "hk",
        timeout_seconds: int = 30,
        verbose: bool = True,
    ) -> None:
        self._api_key = api_key
        self._hl = hl
        self._gl = gl
        self._timeout_seconds = timeout_seconds
        self._verbose = verbose
        self._fast_scan_mode = False
        self._last_quote_meta: dict[str, str | float | None] = {}
        self._should_fallback = False
        self._last_error_message: str | None = None

    def set_verbose(self, verbose: bool) -> None:
        self._verbose = verbose

    def set_fast_scan_mode(self, enabled: bool) -> None:
        self._fast_scan_mode = enabled

    def _log(self, text: str) -> None:
        if self._verbose:
            print(text, flush=True)

    def _request_search(self, params: dict[str, str]) -> dict:
        response = requests.get(
            "https://serpapi.com/search.json",
            params=params,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Google Flights API 响应格式错误")
        error_message = payload.get("error")
        if isinstance(error_message, str) and error_message.strip():
            raise requests.HTTPError(error_message.strip())
        return payload

    def _build_base_params(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
        currency: str,
    ) -> dict[str, str]:
        return {
            "engine": "google_flights",
            "departure_id": origin.upper(),
            "arrival_id": destination.upper(),
            "outbound_date": depart_date.isoformat(),
            "return_date": return_date.isoformat(),
            "currency": currency.upper(),
            "hl": self._hl,
            "gl": self._gl,
            "api_key": self._api_key,
        }

    def _extract_candidates(self, payload: dict) -> list[dict]:
        candidates: list[dict] = []
        for key in ("best_flights", "other_flights"):
            values = payload.get(key)
            if not isinstance(values, list):
                continue
            for item in values:
                if isinstance(item, dict) and isinstance(item.get("price"), (int, float)):
                    candidates.append(item)
        return candidates

    def _pick_best_candidate(self, payload: dict) -> dict | None:
        candidates = self._extract_candidates(payload)
        if not candidates:
            return None
        return min(candidates, key=lambda item: float(item.get("price", 1e12)))

    def _format_minutes(self, minutes: int | float | None) -> str | None:
        if not isinstance(minutes, (int, float)):
            return None
        total = int(minutes)
        hours, mins = divmod(total, 60)
        if hours and mins:
            return f"{hours}h{mins:02d}m"
        if hours:
            return f"{hours}h"
        return f"{mins}m"

    def _format_time(
        self,
        raw_value: str | None,
        base_day: date,
    ) -> str | None:
        if not raw_value:
            return None
        try:
            parsed = datetime.strptime(raw_value, "%Y-%m-%d %H:%M")
        except ValueError:
            return None
        suffix = ""
        delta_days = (parsed.date() - base_day).days
        if delta_days > 0:
            suffix = f"+{delta_days}d"
        return f"{parsed:%H:%M}{suffix}"

    def _journey_from_flights(self, flights: list[dict]) -> str | None:
        airport_ids: list[str] = []
        for flight in flights:
            departure = flight.get("departure_airport")
            arrival = flight.get("arrival_airport")
            if isinstance(departure, dict):
                dep_id = departure.get("id")
                if isinstance(dep_id, str) and dep_id:
                    if not airport_ids or airport_ids[-1] != dep_id:
                        airport_ids.append(dep_id)
            if isinstance(arrival, dict):
                arr_id = arrival.get("id")
                if isinstance(arr_id, str) and arr_id:
                    if not airport_ids or airport_ids[-1] != arr_id:
                        airport_ids.append(arr_id)
        if len(airport_ids) < 2:
            return None
        return "->".join(airport_ids)

    def _stopovers_from_flights(self, flights: list[dict]) -> str | None:
        if len(flights) <= 1:
            return None
        stops: list[str] = []
        for flight in flights[:-1]:
            arrival = flight.get("arrival_airport")
            if not isinstance(arrival, dict):
                continue
            stop_name = arrival.get("id") or arrival.get("name")
            if isinstance(stop_name, str) and stop_name and stop_name not in stops:
                stops.append(stop_name)
        if not stops:
            return None
        return ", ".join(stops)

    def _flight_numbers_from_flights(self, flights: list[dict]) -> str | None:
        codes: list[str] = []
        for flight in flights:
            value = flight.get("flight_number")
            if isinstance(value, str) and value and value not in codes:
                codes.append(value)
        if not codes:
            return None
        return " / ".join(codes)

    def _unique_join_from_flights(
        self,
        flights: list[dict],
        key: str,
    ) -> str | None:
        values: list[str] = []
        for flight in flights:
            value = flight.get(key)
            if isinstance(value, str) and value and value not in values:
                values.append(value)
        if not values:
            return None
        return " / ".join(values)

    def _layover_details(self, candidate: dict) -> str | None:
        layovers = candidate.get("layovers")
        if not isinstance(layovers, list) or not layovers:
            return None

        details: list[str] = []
        for layover in layovers:
            if not isinstance(layover, dict):
                continue
            stop_id = layover.get("id") or layover.get("name")
            duration_text = self._format_minutes(layover.get("duration"))
            if not isinstance(stop_id, str) or not stop_id:
                continue
            part = stop_id
            if duration_text:
                part = f"{part} {duration_text}"
            if layover.get("overnight") is True:
                part = f"{part} overnight"
            details.append(part)
        if not details:
            return None
        return ", ".join(details)

    def _extensions_from_flights(self, flights: list[dict]) -> list[str]:
        values: list[str] = []
        for flight in flights:
            raw_extensions = flight.get("extensions")
            if not isinstance(raw_extensions, list):
                continue
            for item in raw_extensions:
                if isinstance(item, str) and item and item not in values:
                    values.append(item)
        return values

    def _carbon_summary(self, candidate: dict) -> str | None:
        carbon = candidate.get("carbon_emissions")
        if not isinstance(carbon, dict):
            return None
        percent = carbon.get("difference_percent")
        if not isinstance(percent, (int, float)):
            return None
        if percent == 0:
            return "与该航线典型值接近"
        direction = "高" if percent > 0 else "低"
        return f"较该航线典型值{direction}{abs(int(percent))}%"

    def _price_insights_summary(self, payload: dict) -> str | None:
        insights = payload.get("price_insights")
        if not isinstance(insights, dict):
            return None

        parts: list[str] = []
        level = insights.get("price_level")
        if isinstance(level, str) and level:
            parts.append(f"price_level={level}")

        lowest_price = insights.get("lowest_price")
        if isinstance(lowest_price, (int, float)):
            currency = self.quote_currency or ""
            suffix = f" {currency}".rstrip()
            parts.append(f"lowest={float(lowest_price):.0f}{suffix}")

        typical = insights.get("typical_price_range")
        if (
            isinstance(typical, list)
            and len(typical) == 2
            and all(isinstance(item, (int, float)) for item in typical)
        ):
            currency = self.quote_currency or ""
            suffix = f" {currency}".rstrip()
            parts.append(
                f"typical={float(typical[0]):.0f}-{float(typical[1]):.0f}{suffix}"
            )

        if not parts:
            return None
        return ", ".join(parts)

    def _meta_from_candidate(
        self,
        candidate: dict | None,
        base_day: date,
        prefix: str,
    ) -> dict[str, str | float | None]:
        if not isinstance(candidate, dict):
            return {}

        flights = candidate.get("flights")
        if not isinstance(flights, list) or not flights:
            return {}

        first_leg = flights[0]
        last_leg = flights[-1]
        departure_airport = (
            first_leg.get("departure_airport")
            if isinstance(first_leg, dict)
            else None
        )
        arrival_airport = (
            last_leg.get("arrival_airport")
            if isinstance(last_leg, dict)
            else None
        )

        depart_time = None
        arrive_time = None
        if isinstance(departure_airport, dict):
            depart_time = self._format_time(
                departure_airport.get("time"),
                base_day,
            )
        if isinstance(arrival_airport, dict):
            arrive_time = self._format_time(
                arrival_airport.get("time"),
                base_day,
            )

        journey = self._journey_from_flights(flights)
        stopovers = self._stopovers_from_flights(flights)
        meta: dict[str, str | float | None] = {
            f"{prefix}depart_time": depart_time,
            f"{prefix}arrive_time": arrive_time,
            f"{prefix}journey": journey,
            f"{prefix}stopovers": stopovers,
            f"{prefix}stopover_details": self._layover_details(candidate),
            f"{prefix}flight_number": self._flight_numbers_from_flights(flights),
            f"{prefix}airline": self._unique_join_from_flights(flights, "airline"),
            f"{prefix}travel_class": self._unique_join_from_flights(
                flights,
                "travel_class",
            ),
            f"{prefix}airplane": self._unique_join_from_flights(flights, "airplane"),
            f"{prefix}duration": self._format_minutes(candidate.get("total_duration")),
            f"{prefix}extensions": "; ".join(self._extensions_from_flights(flights))
            or None,
            f"{prefix}carbon": self._carbon_summary(candidate),
        }
        return meta

    def get_last_quote_meta(self) -> dict[str, str | float | None]:
        return dict(self._last_quote_meta)

    def should_fallback(self) -> bool:
        return self._should_fallback

    def get_last_error_message(self) -> str | None:
        return self._last_error_message

    def get_roundtrip_price(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
        currency: str,
    ) -> float | None:
        self._last_quote_meta = {}
        self._should_fallback = False
        self._last_error_message = None
        params = self._build_base_params(
            origin=origin,
            destination=destination,
            depart_date=depart_date,
            return_date=return_date,
            currency=currency,
        )
        self._log(
            "[GOOGLE-FLIGHTS] 查询 "
            f"{origin}->{destination} {depart_date}/{return_date} "
            f"fast={self._fast_scan_mode}"
        )

        try:
            outbound_payload = self._request_search(params)
        except requests.RequestException as error:
            self._should_fallback = True
            self._last_error_message = str(error)
            self._log(
                "[WARN] Google Flights 查询失败 "
                f"{origin}->{destination} {depart_date}/{return_date}: {error}"
            )
            return None

        outbound_candidate = self._pick_best_candidate(outbound_payload)
        if outbound_candidate is None:
            self._log(
                "[WARN] Google Flights 无可用航班 "
                f"{origin}->{destination} {depart_date}/{return_date}"
            )
            return None

        outbound_meta = self._meta_from_candidate(
            outbound_candidate,
            base_day=depart_date,
            prefix="",
        )
        flight_number = outbound_meta.pop("flight_number", None)
        self._last_quote_meta = {
            "depart_time": outbound_meta.get("depart_time"),
            "arrive_time": outbound_meta.get("arrive_time"),
            "outbound_journey": outbound_meta.get("journey"),
            "outbound_stopovers": outbound_meta.get("stopovers"),
            "outbound_stopover_details": outbound_meta.get("stopover_details"),
            "outbound_airline": outbound_meta.get("airline"),
            "outbound_travel_class": outbound_meta.get("travel_class"),
            "outbound_airplane": outbound_meta.get("airplane"),
            "outbound_duration": outbound_meta.get("duration"),
            "outbound_extensions": outbound_meta.get("extensions"),
            "outbound_carbon": outbound_meta.get("carbon"),
            "flight_number": flight_number if isinstance(flight_number, str) else None,
            "price_insights": self._price_insights_summary(outbound_payload),
        }
        outbound_price = float(outbound_candidate.get("price", 0.0))
        if self._fast_scan_mode:
            return outbound_price

        departure_token = outbound_candidate.get("departure_token")
        if not isinstance(departure_token, str) or not departure_token:
            return outbound_price

        return_params = dict(params)
        return_params["departure_token"] = departure_token

        try:
            return_payload = self._request_search(return_params)
        except requests.RequestException as error:
            self._should_fallback = True
            self._last_error_message = str(error)
            self._log(
                "[WARN] Google Flights 返程查询失败 "
                f"{origin}->{destination} {depart_date}/{return_date}: {error}"
            )
            return outbound_price

        return_candidate = self._pick_best_candidate(return_payload)
        if return_candidate is None:
            return outbound_price

        return_meta = self._meta_from_candidate(
            return_candidate,
            base_day=return_date,
            prefix="return_",
        )

        return_flight_number = return_meta.pop("return_flight_number", None)
        combined_flight_numbers = [
            value
            for value in (
                self._last_quote_meta.get("flight_number"),
                return_flight_number,
            )
            if isinstance(value, str) and value
        ]
        self._last_quote_meta.update(
            {
                "return_depart_time": return_meta.get("return_depart_time"),
                "return_arrive_time": return_meta.get("return_arrive_time"),
                "return_journey": return_meta.get("return_journey"),
                "return_stopovers": return_meta.get("return_stopovers"),
                "return_stopover_details": return_meta.get(
                    "return_stopover_details"
                ),
                "return_airline": return_meta.get("return_airline"),
                "return_travel_class": return_meta.get("return_travel_class"),
                "return_airplane": return_meta.get("return_airplane"),
                "return_duration": return_meta.get("return_duration"),
                "return_extensions": return_meta.get("return_extensions"),
                "return_carbon": return_meta.get("return_carbon"),
                "flight_number": " / ".join(combined_flight_numbers)
                if combined_flight_numbers
                else None,
            }
        )

        return float(return_candidate.get("price", outbound_price))
