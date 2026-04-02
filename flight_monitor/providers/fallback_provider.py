from datetime import date

from flight_monitor.providers.base import PriceProvider


class FallbackPriceProvider(PriceProvider):
    def __init__(
        self,
        primary: PriceProvider,
        fallback: PriceProvider,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._active_provider = primary
        self._using_fallback = False
        self._verbose = True
        self._fast_scan_mode = False

    @property
    def name(self) -> str:
        if self._using_fallback:
            return f"{self._primary.name}->fallback:{self._fallback.name}"
        return self._primary.name

    @property
    def quote_currency(self) -> str | None:
        return getattr(self._active_provider, "quote_currency", None)

    def set_verbose(self, verbose: bool) -> None:
        self._verbose = verbose
        for provider in (self._primary, self._fallback):
            setter = getattr(provider, "set_verbose", None)
            if callable(setter):
                setter(verbose)

    def set_fast_scan_mode(self, enabled: bool) -> None:
        self._fast_scan_mode = enabled
        for provider in (self._primary, self._fallback):
            setter = getattr(provider, "set_fast_scan_mode", None)
            if callable(setter):
                setter(enabled)

    def _log(self, text: str) -> None:
        if self._verbose:
            print(text, flush=True)

    def _primary_should_fallback(self) -> bool:
        checker = getattr(self._primary, "should_fallback", None)
        return bool(callable(checker) and checker())

    def _primary_fallback_reason(self) -> str | None:
        getter = getattr(self._primary, "get_last_error_message", None)
        if not callable(getter):
            return None
        value = getter()
        return value if isinstance(value, str) and value else None

    def _activate_fallback(self) -> None:
        if self._using_fallback:
            return
        self._using_fallback = True
        self._active_provider = self._fallback
        reason = self._primary_fallback_reason()
        if reason:
            self._log(
                "[PROVIDER] Google Flights 不可用，自动切换到 "
                f"{self._fallback.name}: {reason}"
            )
        else:
            self._log(
                "[PROVIDER] Google Flights 不可用，自动切换到 "
                f"{self._fallback.name}"
            )

    def get_last_quote_meta(self) -> dict[str, str | float | None]:
        return self._active_provider.get_last_quote_meta()

    def get_roundtrip_price(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
        currency: str,
    ) -> float | None:
        if self._using_fallback:
            return self._fallback.get_roundtrip_price(
                origin=origin,
                destination=destination,
                depart_date=depart_date,
                return_date=return_date,
                currency=currency,
            )

        price = self._primary.get_roundtrip_price(
            origin=origin,
            destination=destination,
            depart_date=depart_date,
            return_date=return_date,
            currency=currency,
        )
        if self._primary_should_fallback():
            self._activate_fallback()
            return self._fallback.get_roundtrip_price(
                origin=origin,
                destination=destination,
                depart_date=depart_date,
                return_date=return_date,
                currency=currency,
            )

        self._active_provider = self._primary
        return price
