import re
import time
from datetime import date

from playwright.sync_api import sync_playwright

from flight_monitor.providers.base import PriceProvider


class TripScrapePriceProvider(PriceProvider):
    name = "trip_scrape"
    quote_currency = "USD"

    city_slug_by_iata = {
        "CAN": "guangzhou",
        "SZX": "shenzhen",
        "HKG": "hong-kong",
        "PQC": "phu-quoc-island",
    }

    def __init__(
        self,
        timeout_seconds: int = 60,
        render_wait_ms: int = 12000,
        max_retries: int = 3,
        verbose: bool = True,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._render_wait_ms = render_wait_ms
        self._max_retries = max_retries
        self._last_quote_meta: dict[str, str | float | None] = {}
        self._verbose = verbose

    def set_verbose(self, verbose: bool) -> None:
        self._verbose = verbose

    def _log(self, text: str) -> None:
        if self._verbose:
            print(text, flush=True)

    def _build_trip_url(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
    ) -> str:
        origin_upper = origin.upper()
        destination_upper = destination.upper()
        return (
            "https://www.trip.com/flights/showfarefirst"
            f"?dcity={origin_upper}"
            f"&acity={destination_upper}"
            f"&ddate={depart_date.isoformat()}"
            f"&rdate={return_date.isoformat()}"
            "&triptype=rt&class=y&lowpricesource=searchform"
        )

    def _extract_min_price(self, page_text: str) -> float | None:
        raw_numbers = re.findall(
            r"(?:US\$|\$|¥|￥|CNY\s?)\s?([0-9][0-9,]{1,6})",
            page_text,
        )
        prices = [
            float(value.replace(",", ""))
            for value in raw_numbers
            if 40 <= float(value.replace(",", "")) <= 100000
        ]
        if not prices:
            return None
        return min(prices)

    def _extract_price_token_value(self, text: str) -> float | None:
        match = re.search(r"(?:US\$|\$|¥|￥|CNY\s?)\s?([0-9][0-9,]{1,6})", text)
        if not match:
            return None
        return float(match.group(1).replace(",", ""))

    def _extract_roundtrip_calendar_price(
        self,
        page_text: str,
        depart_date: date,
        return_date: date,
    ) -> float | None:
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        depart_label = depart_date.strftime("%b %-d")
        return_label = return_date.strftime("%b %-d")
        targets = {
            f"{depart_label}–{return_label}",
            f"{depart_label}-{return_label}",
            f"{depart_label} – {return_label}",
            f"{depart_label} - {return_label}",
        }

        for index, line in enumerate(lines):
            if line not in targets:
                continue

            for offset in (1, -1, 2, -2):
                probe = index + offset
                if probe < 0 or probe >= len(lines):
                    continue
                if lines[probe].lower() == "view":
                    continue
                price = self._extract_price_token_value(lines[probe])
                if price is not None:
                    return price

        return None

    def _extract_result_list_price(self, page_text: str) -> float | None:
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        start_idx = None
        for index, line in enumerate(lines):
            if "1. departures to" in line.lower():
                start_idx = index
                break
        if start_idx is None:
            return None

        for probe in range(start_idx, min(len(lines), start_idx + 80)):
            price = self._extract_price_token_value(lines[probe])
            if price is not None:
                return price
        return None

    def _extract_times(self, page_text: str) -> tuple[str | None, str | None]:
        pairs = re.findall(
            r"\b([0-2][0-9]:[0-5][0-9])\s*[–-]\s*"
            r"([0-2][0-9]:[0-5][0-9](?:\+[0-9]+d)?)",
            page_text,
        )
        for depart_time, arrive_time in pairs:
            if depart_time in {"00:00", "24:00"}:
                continue
            if arrive_time.startswith("00:00") or arrive_time.startswith(
                "24:00"
            ):
                continue
            return depart_time, arrive_time

        singles = re.findall(
            r"\b([0-2][0-9]:[0-5][0-9](?:\+[0-9]+d)?)\b",
            page_text,
        )
        filtered = [
            value
            for value in singles
            if not value.startswith("00:00") and not value.startswith("24:00")
        ]
        if len(filtered) >= 2:
            return filtered[0], filtered[1]
        return None, None

    def _extract_flight_number(
        self,
        page_text: str,
        page_html: str,
    ) -> str | None:
        ignore_context_keywords = {
            "e.g.",
            "example",
            "provide",
            "valid flight number",
        }

        candidates: list[str] = []
        for match in re.finditer(
            r"\b([A-Z]{2}\s?[0-9]{2,4})\b",
            page_text,
        ):
            value = match.group(1).replace(" ", "")
            if value == "CZ1235":
                continue
            left = max(match.start() - 40, 0)
            right = min(match.end() + 40, len(page_text))
            context = page_text[left:right].lower()
            if any(token in context for token in ignore_context_keywords):
                continue
            candidates.append(value)

        if candidates:
            return candidates[0]
        return None

    def _find_section(
        self,
        lines: list[str],
        start_keywords: tuple[str, ...],
        end_keywords: tuple[str, ...] = (),
    ) -> list[str]:
        start_idx = None
        for index, line in enumerate(lines):
            lower_line = line.lower()
            if any(keyword in lower_line for keyword in start_keywords):
                start_idx = index
                break
        if start_idx is None:
            return []

        end_idx = len(lines)
        if end_keywords:
            for index in range(start_idx + 1, len(lines)):
                lower_line = lines[index].lower()
                if any(keyword in lower_line for keyword in end_keywords):
                    end_idx = index
                    break
        return lines[start_idx:end_idx]

    def _extract_times_from_lines(
        self,
        lines: list[str],
    ) -> tuple[str | None, str | None]:
        section_text = "\n".join(lines)
        pairs = re.findall(
            r"\b([0-2][0-9]:[0-5][0-9])\s*[–-]\s*"
            r"([0-2][0-9]:[0-5][0-9](?:\+[0-9]+d)?)",
            section_text,
        )
        for depart_time, arrive_time in pairs:
            if depart_time in {"00:00", "24:00"}:
                continue
            if arrive_time.startswith("00:00") or arrive_time.startswith("24:00"):
                continue
            return depart_time, arrive_time

        singles = re.findall(
            r"\b([0-2][0-9]:[0-5][0-9](?:\+[0-9]+d)?)\b",
            section_text,
        )
        filtered = [
            value
            for value in singles
            if not value.startswith("00:00") and not value.startswith("24:00")
        ]
        if len(filtered) >= 2:
            return filtered[0], filtered[1]
        return None, None

    def _extract_journey_and_stopovers(
        self,
        lines: list[str],
    ) -> tuple[str | None, str | None]:
        journey = None
        stops = []

        for line in lines:
            if " – " in line and journey is None and "Flights" not in line:
                journey = line
            stop_match = re.search(
                r"\bin\s+([A-Za-z][A-Za-z\s\-']+)",
                line,
            )
            if stop_match:
                stops.append(stop_match.group(1).strip())

        dedup_stops: list[str] = []
        for value in stops:
            if value not in dedup_stops:
                dedup_stops.append(value)

        stopover_text = ", ".join(dedup_stops) if dedup_stops else None
        return journey, stopover_text

    def _extract_stopover_details(
        self,
        lines: list[str],
    ) -> str | None:
        details: list[str] = []
        seen: set[str] = set()

        for line in lines:
            lower_line = line.lower()
            if "stop" not in lower_line and " in " not in lower_line:
                continue

            city_match = re.search(
                r"\bin\s+([A-Za-z][A-Za-z\s\-']+)",
                line,
            )
            city = city_match.group(1).strip() if city_match else None

            duration_match = re.search(
                r"\b([0-9]{1,2}h(?:\s*[0-9]{1,2}m)?)\b",
                line,
            )
            duration = duration_match.group(1).replace("  ", " ") if duration_match else None

            time_pair_match = re.search(
                r"\b([0-2][0-9]:[0-5][0-9])\s*[–-]\s*"
                r"([0-2][0-9]:[0-5][0-9](?:\+[0-9]+d)?)",
                line,
            )
            time_pair = (
                f"{time_pair_match.group(1)}-{time_pair_match.group(2)}"
                if time_pair_match
                else None
            )

            if not city and not duration and not time_pair:
                continue

            parts: list[str] = []
            if city:
                parts.append(city)
            if time_pair:
                parts.append(f"{time_pair}")
            if duration:
                parts.append(f"停留{duration}")

            detail = " ".join(parts).strip()
            if detail and detail not in seen:
                seen.add(detail)
                details.append(detail)

        if not details:
            return None
        return "; ".join(details)

    def _extract_extended_meta(
        self,
        page_text: str,
        page_html: str,
    ) -> dict[str, str | float | None]:
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]

        outbound_section = self._find_section(
            lines,
            start_keywords=("1. departures", "departures to"),
            end_keywords=("2. returning", "returning to"),
        )
        return_section = self._find_section(
            lines,
            start_keywords=("2. returning", "returning to"),
        )

        outbound_depart, outbound_arrive = self._extract_times_from_lines(
            outbound_section if outbound_section else lines
        )
        return_depart, return_arrive = self._extract_times_from_lines(
            return_section if return_section else lines
        )

        outbound_journey, outbound_stopovers = self._extract_journey_and_stopovers(
            outbound_section if outbound_section else lines
        )
        return_journey, return_stopovers = self._extract_journey_and_stopovers(
            return_section if return_section else lines
        )
        outbound_stopover_details = self._extract_stopover_details(
            outbound_section if outbound_section else lines
        )
        return_stopover_details = self._extract_stopover_details(
            return_section if return_section else lines
        )

        flight_number = self._extract_flight_number(page_text, page_html)

        return {
            "depart_time": outbound_depart,
            "arrive_time": outbound_arrive,
            "flight_number": flight_number,
            "return_depart_time": return_depart,
            "return_arrive_time": return_arrive,
            "outbound_journey": outbound_journey,
            "return_journey": return_journey,
            "outbound_stopovers": outbound_stopovers,
            "return_stopovers": return_stopovers,
            "outbound_stopover_details": outbound_stopover_details,
            "return_stopover_details": return_stopover_details,
        }

    def _click_first_if_present(
        self,
        page,
        text: str,
        delay_ms: int = 2500,
    ) -> bool:
        locator = page.get_by_text(text, exact=False)
        count = locator.count()
        if count <= 0:
            return False
        try:
            locator.first.click(timeout=3500)
            page.wait_for_timeout(delay_ms)
            return True
        except Exception:
            return False

    def _click_nth_if_present(
        self,
        page,
        text: str,
        index: int,
        delay_ms: int = 2500,
    ) -> bool:
        locator = page.get_by_text(text, exact=False)
        count = locator.count()
        if count <= index:
            return False
        try:
            locator.nth(index).click(timeout=3500)
            page.wait_for_timeout(delay_ms)
            return True
        except Exception:
            return False

    def _collect_page_snapshot(self, page) -> tuple[str, str]:
        return page.inner_text("body"), page.content()

    def _auto_scroll_to_load(self, page) -> None:
        try:
            page.evaluate(
                """() => {
                    return new Promise((resolve) => {
                        let y = 0;
                        const step = 1200;
                        const timer = setInterval(() => {
                            y += step;
                            window.scrollTo(0, y);
                            if (y >= document.body.scrollHeight) {
                                clearInterval(timer);
                                resolve(true);
                            }
                        }, 220);
                    });
                }"""
            )
            page.wait_for_timeout(1600)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(900)
        except Exception:
            return

    def _extract_from_loaded_page(
        self,
        page,
        depart_date: date,
        return_date: date,
    ) -> tuple[float | None, dict[str, str | float | None]]:
        snapshots: list[tuple[str, str, str]] = []
        initial_text, initial_html = self._collect_page_snapshot(page)
        snapshots.append((initial_text, initial_html, "initial"))
        calendar_price = self._extract_roundtrip_calendar_price(
            page_text=initial_text,
            depart_date=depart_date,
            return_date=return_date,
        )

        if self._click_first_if_present(page, "Select", delay_ms=3500):
            text, html = self._collect_page_snapshot(page)
            snapshots.append((text, html, "selected"))

            if self._click_nth_if_present(page, "Select", index=1, delay_ms=3500):
                text, html = self._collect_page_snapshot(page)
                snapshots.append((text, html, "selected"))

            if self._click_first_if_present(
                page,
                "Change Flight",
                delay_ms=2500,
            ):
                text, html = self._collect_page_snapshot(page)
                snapshots.append((text, html, "selected"))

        self._auto_scroll_to_load(page)
        text, html = self._collect_page_snapshot(page)
        snapshots.append((text, html, "scrolled"))

        for step_text in (
            "Included",
            "Change Flight",
            "View details",
            "Details",
            "Flight details",
        ):
            if self._click_first_if_present(page, step_text, delay_ms=1800):
                text, html = self._collect_page_snapshot(page)
                snapshots.append((text, html, "selected"))

        best_price: float | None = None
        best_meta: dict[str, str | float | None] = {}

        for text, html, phase in snapshots:
            if phase in {"selected", "scrolled"}:
                price = self._extract_result_list_price(text)
                if price is None:
                    price = self._extract_min_price(text)
            else:
                price = None
            if price is None:
                continue

            extended_meta = self._extract_extended_meta(text, html)
            if best_price is None:
                best_price = price
            if best_meta == {} or (
                not best_meta.get("return_depart_time")
                and extended_meta.get("return_depart_time")
            ):
                best_meta = extended_meta

        if best_price is None:
            best_price = calendar_price
            if best_meta == {}:
                best_meta = self._extract_extended_meta(initial_text, initial_html)

        return best_price, best_meta

    def get_last_quote_meta(self) -> dict[str, str | float | None]:
        return dict(self._last_quote_meta)

    def get_roundtrip_price(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
        currency: str,
    ) -> float | None:
        self._last_quote_meta = {}
        url = self._build_trip_url(
            origin=origin,
            destination=destination,
            depart_date=depart_date,
            return_date=return_date,
        )

        for attempt in range(1, self._max_retries + 1):
            self._log(
                "[SCRAPE] 开始抓取 "
                f"{origin}->{destination} {depart_date}/{return_date} "
                f"attempt={attempt}/{self._max_retries}",
            )
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(
                        user_agent=(
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/122.0.0.0 Safari/537.36"
                        )
                    )
                    page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self._timeout_seconds * 1000,
                    )
                    page.wait_for_timeout(self._render_wait_ms)
                    price, meta = self._extract_from_loaded_page(
                        page,
                        depart_date=depart_date,
                        return_date=return_date,
                    )
                    browser.close()
            except Exception as error:
                self._log(
                    "[WARN] Trip 抓取失败 "
                    f"{origin}->{destination} {depart_date}/{return_date} "
                    f"attempt={attempt}: {error}"
                )
                time.sleep(min(attempt * 1.5, 5))
                continue

            if price is not None:
                self._last_quote_meta = dict(meta)
                self._log(
                    "[SCRAPE] 抓取成功 "
                    f"{origin}->{destination} {depart_date}/{return_date} "
                    f"price={price}",
                )
                return price

            self._log(
                "[WARN] Trip 页面未解析到价格 "
                f"{origin}->{destination} {depart_date}/{return_date} "
                f"attempt={attempt}"
            )
            time.sleep(min(attempt * 1.5, 5))

        return None
