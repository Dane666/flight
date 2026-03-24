from abc import ABC, abstractmethod
from datetime import date


class PriceProvider(ABC):
    name = "base"
    quote_currency: str | None = None

    @abstractmethod
    def get_roundtrip_price(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
        currency: str,
    ) -> float | None:
        pass

    def get_last_quote_meta(self) -> dict[str, str | float | None]:
        return {}
