import atexit
import re
import time
from datetime import date

from playwright.sync_api import sync_playwright

from flight_monitor.providers.base import PriceProvider


class TripScrapePriceProvider(PriceProvider):
    name = "trip_scrape"
    quote_currency = "USD"
    mobile_user_agent = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 "
        "Mobile/15E148 Safari/604.1"
    )

    city_slug_by_iata = {
        "CAN": "guangzhou",
        "SZX": "shenzhen",
        "HKG": "hong-kong",
        "PQC": "phu-quoc-island",
    }
    stopover_ignore_phrases = (
        "save money",
        "registering",
        "sign in",
        "log in",
        "price alert",
        "member",
        "discount",
    )

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
        self._playwright = None
        self._browser = None
        self._context = None
        self._cleanup_registered = False
        self._fast_scan_mode = False

    def set_verbose(self, verbose: bool) -> None:
        self._verbose = verbose

    def set_fast_scan_mode(self, enabled: bool) -> None:
        self._fast_scan_mode = enabled

    def _log(self, text: str) -> None:
        if self._verbose:
            print(text, flush=True)

    def _cleanup_browser(self) -> None:
        context = self._context
        browser = self._browser
        playwright = self._playwright
        self._context = None
        self._browser = None
        self._playwright = None

        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass

    def _ensure_context(self):
        if self._context is not None:
            return self._context

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            user_agent=self.mobile_user_agent,
            locale="en-US",
            viewport={"width": 430, "height": 932},
            screen={"width": 430, "height": 932},
            is_mobile=True,
            has_touch=True,
            device_scale_factor=3,
        )
        self._context.set_extra_http_headers(
            {
                "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        self._context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in {"image", "media", "font"}
            else route.continue_(),
        )
        if not self._cleanup_registered:
            atexit.register(self._cleanup_browser)
            self._cleanup_registered = True
        return self._context

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

    def _extract_price_token_values(self, text: str) -> list[float]:
        matches = re.findall(
            r"(?:US\$|\$|¥|￥|CNY\s?)\s?([0-9][0-9,]{1,6})",
            text,
        )
        prices = [
            float(value.replace(",", ""))
            for value in matches
            if 40 <= float(value.replace(",", "")) <= 100000
        ]
        deduped: list[float] = []
        for price in prices:
            if price not in deduped:
                deduped.append(price)
        return deduped

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

        prices: list[float] = []
        for probe in range(start_idx, min(len(lines), start_idx + 80)):
            prices.extend(self._extract_price_token_values(lines[probe]))
        if not prices:
            return None
        return min(prices)

    def _extract_dom_lowest_price(self, page) -> float | None:
        selectors = [
            "[class*='price']",
            "[data-testid*='price']",
            "[class*='fare']",
            "[class*='money']",
        ]
        candidates: list[float] = []
        for selector in selectors:
            try:
                chunks = page.eval_on_selector_all(
                    selector,
                    "elements => elements.map(e => (e.textContent || '').trim()).filter(Boolean)",
                )
            except Exception:
                continue
            if not isinstance(chunks, list):
                continue
            for chunk in chunks:
                if not isinstance(chunk, str):
                    continue
                candidates.extend(self._extract_price_token_values(chunk))
        if not candidates:
            return None
        return min(candidates)

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
        page=None,
    ) -> str | None:
        ignore_context_keywords = {
            "e.g.",
            "example",
            "provide",
            "valid flight number",
            "for example",
            "sample",
        }

        keyword_patterns = [
            re.compile(
                r"(?i)\bflight(?:\s*no\.?|\s*number|\s*#)?\s*[:：]?\s*"
                r"([A-Z0-9]{2}\s*[- ]?\s*[0-9]{2,4}[A-Z]?)\b"
            ),
            re.compile(
                r"航班(?:号|編號|编号)?\s*[:：]?\s*"
                r"([A-Z0-9]{2}\s*[- ]?\s*[0-9]{2,4}[A-Z]?)"
            ),
        ]
        generic_pattern = re.compile(
            r"\b([A-Z0-9]{2}\s*[- ]?\s*[0-9]{2,4}[A-Z]?)\b"
        )

        def normalize(code: str) -> str | None:
            compact = re.sub(r"[^A-Z0-9]", "", code.upper())
            if not re.fullmatch(r"[A-Z0-9]{2}[0-9]{2,4}[A-Z]?", compact):
                return None
            if compact in {"CZ1235"}:
                return None
            if compact[:2].isdigit():
                return None
            if compact.startswith(("US", "HK", "CN", "TH", "TW", "SG")):
                if compact[2:].isdigit() and len(compact) <= 5:
                    return None
            return compact

        def collect_from_text(
            text: str,
            prioritized: bool,
        ) -> list[str]:
            values: list[str] = []
            patterns = keyword_patterns if prioritized else [generic_pattern]
            for pattern in patterns:
                for match in pattern.finditer(text):
                    raw = match.group(1)
                    normalized = normalize(raw)
                    if not normalized:
                        continue
                    left = max(match.start() - 60, 0)
                    right = min(match.end() + 60, len(text))
                    context = text[left:right].lower()
                    if any(token in context for token in ignore_context_keywords):
                        continue
                    values.append(normalized)
            return values

        candidates: list[str] = []
        candidates.extend(collect_from_text(page_text, prioritized=True))

        if page is not None:
            try:
                dom_chunks = page.eval_on_selector_all(
                    "[class*='flight'], [class*='segment'], [class*='airline'], "
                    "[data-testid*='flight'], [aria-label*='flight']",
                    "elements => elements.map(e => (e.textContent || '').trim()).filter(Boolean)",
                )
                if isinstance(dom_chunks, list) and dom_chunks:
                    dom_text = "\n".join(
                        chunk for chunk in dom_chunks if isinstance(chunk, str)
                    )
                    candidates.extend(collect_from_text(dom_text, prioritized=True))
                    candidates.extend(collect_from_text(dom_text, prioritized=False))
            except Exception:
                pass

        candidates.extend(collect_from_text(page_html, prioritized=True))
        candidates.extend(collect_from_text(page_text, prioritized=False))
        candidates.extend(collect_from_text(page_html, prioritized=False))

        deduped: list[str] = []
        for code in candidates:
            if code not in deduped:
                deduped.append(code)

        if deduped:
            return deduped[0]
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
            lower_line = line.lower()
            if not any(
                token in lower_line
                for token in ("stop", "layover", "transfer", "中转", "经停")
            ):
                continue
            stop_match = re.search(
                r"\bin\s+([A-Za-z][A-Za-z\s\-']+)",
                line,
            )
            if stop_match:
                city = stop_match.group(1).strip()
                city_lower = city.lower()
                if any(
                    phrase in city_lower
                    for phrase in self.stopover_ignore_phrases
                ):
                    continue
                stops.append(city)

        dedup_stops: list[str] = []
        for value in stops:
            if value not in dedup_stops:
                dedup_stops.append(value)
            if len(dedup_stops) >= 2:
                break

        stopover_text = ", ".join(dedup_stops) if dedup_stops else None
        return journey, stopover_text

    def _extract_stopover_details(
        self,
        lines: list[str],
        journey_hint: str | None = None,
    ) -> str | None:
        time_tokens: list[str] = []
        if journey_hint:
            for token in re.findall(r"\b[0-2][0-9]:[0-5][0-9](?:\+[0-9]+d)?\b", journey_hint):
                if token not in time_tokens:
                    time_tokens.append(token)

        details: list[str] = []
        seen: set[str] = set()

        for line in lines:
            lower_line = line.lower()
            if not any(
                token in lower_line
                for token in ("stop", "layover", "transfer", "中转", "经停")
            ):
                continue

            if time_tokens and not any(token in line for token in time_tokens):
                continue

            city_match = re.search(
                r"\bin\s+([A-Za-z][A-Za-z\s\-']+)",
                line,
            )
            city = city_match.group(1).strip() if city_match else None
            if city and any(
                phrase in city.lower()
                for phrase in self.stopover_ignore_phrases
            ):
                city = None

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
                if len(details) >= 2:
                    break

        if not details:
            return None
        return "; ".join(details)

    def _extract_extended_meta(
        self,
        page_text: str,
        page_html: str,
        page=None,
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
            outbound_section if outbound_section else lines,
            journey_hint=outbound_journey,
        )
        return_stopover_details = self._extract_stopover_details(
            return_section if return_section else lines,
            journey_hint=return_journey,
        )

        flight_number = self._extract_flight_number(
            page_text,
            page_html,
            page=page,
        )

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

    def _wait_for_search_results(self, page) -> None:
        deadline = time.monotonic() + (self._render_wait_ms / 1000)
        while time.monotonic() < deadline:
            try:
                body_text = page.inner_text("body")
            except Exception:
                page.wait_for_timeout(700)
                continue

            lower_text = body_text.lower()
            if (
                re.search(r"(?:US\$|\$|¥|￥|CNY\s?)\s?[0-9][0-9,]{1,6}", body_text)
                or "select" in lower_text
                or "included" in lower_text
                or "view details" in lower_text
                or "flight details" in lower_text
            ):
                return
            page.wait_for_timeout(700)

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

        if not self._fast_scan_mode:
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

        if not self._fast_scan_mode:
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
            phase_prices: list[float] = []
            if phase in {"selected", "scrolled"}:
                price = self._extract_result_list_price(text)
                if price is None:
                    price = self._extract_min_price(text)
                if price is not None:
                    phase_prices.append(price)
                dom_price = self._extract_dom_lowest_price(page)
                if dom_price is not None:
                    phase_prices.append(dom_price)
            if not phase_prices:
                continue
            price = min(phase_prices)

            if self._fast_scan_mode:
                if best_price is None or price < best_price:
                    best_price = price
                continue

            extended_meta = self._extract_extended_meta(text, html, page=page)
            if best_price is None or price < best_price:
                best_price = price
                best_meta = extended_meta
            elif best_meta == {} or (
                not best_meta.get("return_depart_time")
                and extended_meta.get("return_depart_time")
            ):
                best_meta = extended_meta

        if best_price is None:
            best_price = calendar_price
            if best_meta == {}:
                best_meta = self._extract_extended_meta(
                    initial_text,
                    initial_html,
                    page=page,
                )

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
                context = self._ensure_context()
                page = context.new_page()
                page.set_default_timeout(self._timeout_seconds * 1000)
                try:
                    page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self._timeout_seconds * 1000,
                    )
                    self._wait_for_search_results(page)
                    price, meta = self._extract_from_loaded_page(
                        page,
                        depart_date=depart_date,
                        return_date=return_date,
                    )
                finally:
                    try:
                        page.close()
                    except Exception:
                        pass
            except Exception as error:
                self._cleanup_browser()
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
