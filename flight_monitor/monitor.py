import time
from datetime import date, datetime, timedelta
import re

from flight_monitor.config import AppConfig
from flight_monitor.fx import FxConverter
from flight_monitor.models import PriceQuote, Route
from flight_monitor.notifier import (
    AlertMessage,
    ConsoleNotifier,
    EmailNotifier,
    FeishuNotifier,
)
from flight_monitor.providers.base import PriceProvider
from flight_monitor.storage import PriceStorage


def build_roundtrip_pairs(window_start: date, window_end: date) -> list[tuple[date, date]]:
    if window_end <= window_start:
        raise ValueError("window_end 必须晚于 window_start")

    all_days: list[date] = []
    current = window_start
    while current <= window_end:
        all_days.append(current)
        current += timedelta(days=1)

    pairs: list[tuple[date, date]] = []
    for depart_day in all_days:
        for return_day in all_days:
            if return_day > depart_day:
                pairs.append((depart_day, return_day))
    return pairs


class FlightMonitor:
    def __init__(
        self,
        config: AppConfig,
        provider: PriceProvider,
        storage: PriceStorage,
        notifier: ConsoleNotifier | EmailNotifier | FeishuNotifier,
    ) -> None:
        self.config = config
        self.provider = provider
        self.storage = storage
        self.notifier = notifier
        self.fx_converter = FxConverter()

    def _is_missing_text(self, value: str | None) -> bool:
        if value is None:
            return True
        text = value.strip()
        if not text:
            return True
        normalized = text.upper()
        return normalized in {"N/A", "APPROX", "UNKNOWN", "--"}

    def _candidate_is_direct(
        self,
        candidate: dict[str, str | float | None],
    ) -> bool:
        stop_texts = [
            candidate.get("outbound_stopovers"),
            candidate.get("return_stopovers"),
            candidate.get("outbound_stopover_details"),
            candidate.get("return_stopover_details"),
        ]
        for value in stop_texts:
            if isinstance(value, str) and not self._is_missing_text(value):
                return False
        return True

    def _extract_layover_hours(self, text: str | None) -> list[float]:
        if not isinstance(text, str) or self._is_missing_text(text):
            return []
        result: list[float] = []
        for match in re.finditer(r"([0-9]{1,2})h(?:\s*([0-9]{1,2})m)?", text):
            hours = int(match.group(1))
            minutes = int(match.group(2) or "0")
            result.append(hours + minutes / 60)
        return result

    def _candidate_layover_within_limit(
        self,
        candidate: dict[str, str | float | None],
        max_hours: float = 3.0,
    ) -> bool:
        if self._candidate_is_direct(candidate):
            return True

        durations = [
            *self._extract_layover_hours(
                candidate.get("outbound_stopover_details")
                if isinstance(candidate.get("outbound_stopover_details"), str)
                else None
            ),
            *self._extract_layover_hours(
                candidate.get("return_stopover_details")
                if isinstance(candidate.get("return_stopover_details"), str)
                else None
            ),
        ]
        if not durations:
            return False
        return max(durations) <= max_hours

    def _candidate_max_layover_hours(
        self,
        candidate: dict[str, str | float | None],
    ) -> float | None:
        durations = [
            *self._extract_layover_hours(
                candidate.get("outbound_stopover_details")
                if isinstance(candidate.get("outbound_stopover_details"), str)
                else None
            ),
            *self._extract_layover_hours(
                candidate.get("return_stopover_details")
                if isinstance(candidate.get("return_stopover_details"), str)
                else None
            ),
        ]
        if not durations:
            return None
        return max(durations)

    def _evaluate_price_position(
        self,
        current_price: float,
        stats: dict[str, float | int | None],
    ) -> str:
        count = int(stats.get("count") or 0)
        historical_min = stats.get("min")
        historical_max = stats.get("max")

        if historical_min is None or historical_max is None or count == 0:
            return "新样本"

        if historical_max == historical_min:
            return "低位"

        ratio = (current_price - historical_min) / (
            historical_max - historical_min
        )
        if ratio <= 0.33:
            return "低位"
        if ratio >= 0.66:
            return "高位"
        return "中位"

    def _is_depart_time_allowed(self, depart_time: str | None) -> bool:
        min_depart_time = self.config.min_depart_time
        if not min_depart_time:
            return True
        if not depart_time:
            return False

        depart_hhmm = depart_time.split("+")[0]
        try:
            depart_dt = datetime.strptime(depart_hhmm, "%H:%M")
            min_dt = datetime.strptime(min_depart_time, "%H:%M")
        except ValueError:
            return True
        return depart_dt >= min_dt

    def _get_active_date_pair(self) -> tuple[date, date]:
        if self.config.fixed_depart_date and self.config.fixed_return_date:
            return self.config.fixed_depart_date, self.config.fixed_return_date
        pairs = build_roundtrip_pairs(
            window_start=self.config.window_start,
            window_end=self.config.window_end,
        )
        if not pairs:
            raise ValueError("没有可用的去返日期组合")
        return pairs[0]

    def run_once(self, quick: bool = False) -> None:
        print("[RUN] 开始执行 run-once", flush=True)
        if self.config.fixed_depart_date and self.config.fixed_return_date:
            pairs = [
                (self.config.fixed_depart_date, self.config.fixed_return_date)
            ]
            print(
                "[RUN] 使用固定去返日期 "
                f"{self.config.fixed_depart_date}/{self.config.fixed_return_date}",
                flush=True,
            )
        else:
            pairs = build_roundtrip_pairs(
                window_start=self.config.window_start,
                window_end=self.config.window_end,
            )
        if quick:
            pairs = pairs[:1]
            print(
                "[RUN] quick 模式已启用：每个出发地仅抓取 1 个日期组合",
                flush=True,
            )
        print(
            f"[RUN] 监控组合数: origins={len(self.config.origins)}, pairs={len(pairs)}",
            flush=True,
        )

        for origin in self.config.origins:
            route = Route(origin=origin, destination=self.config.destination)
            for depart_date, return_date in pairs:
                print(
                    "[RUN] 查询 "
                    f"{origin}->{self.config.destination} "
                    f"{depart_date}/{return_date}",
                    flush=True,
                )
                source_price = self.provider.get_roundtrip_price(
                    origin=origin,
                    destination=self.config.destination,
                    depart_date=depart_date,
                    return_date=return_date,
                    currency=self.config.currency,
                )
                if source_price is None:
                    print(
                        "[RUN] 未获取到价格 "
                        f"{origin}->{self.config.destination} "
                        f"{depart_date}/{return_date}",
                        flush=True,
                    )
                    continue

                source_currency = (
                    getattr(self.provider, "quote_currency", None)
                    or self.config.currency
                )
                target_currency = self.config.currency
                exchange_rate = 1.0
                converted_price = source_price

                if source_currency != target_currency:
                    converted_price, exchange_rate = self.fx_converter.convert(
                        amount=source_price,
                        base=source_currency,
                        target=target_currency,
                    )

                meta = self.provider.get_last_quote_meta()
                historical_stats = self.storage.get_price_stats(
                    route=route,
                    depart_date=depart_date.isoformat(),
                    return_date=return_date.isoformat(),
                    currency=target_currency,
                    provider=self.provider.name,
                    source_currency=source_currency,
                )
                position_text = self._evaluate_price_position(
                    current_price=converted_price,
                    stats=historical_stats,
                )

                quote = PriceQuote(
                    route=route,
                    depart_date=depart_date,
                    return_date=return_date,
                    total_price=converted_price,
                    currency=target_currency,
                    provider=self.provider.name,
                    observed_at=datetime.now(),
                    depart_time=(meta.get("depart_time") or None),
                    arrive_time=(meta.get("arrive_time") or None),
                    flight_number=(meta.get("flight_number") or None),
                    source_price=source_price,
                    source_currency=source_currency,
                    exchange_rate=exchange_rate,
                    price_position=position_text,
                )

                if not self._is_depart_time_allowed(quote.depart_time):
                    print(
                        "[RUN] 跳过（不满足最早起飞时间） "
                        f"{origin}->{self.config.destination} "
                        f"{depart_date}/{return_date} "
                        f"dep={quote.depart_time} "
                        f"min={self.config.min_depart_time}",
                        flush=True,
                    )
                    continue

                self.storage.save_quote(quote)

                historical_low = self.storage.get_historical_low(
                    route=route,
                    depart_date=depart_date.isoformat(),
                    return_date=return_date.isoformat(),
                )

                if quote.total_price <= self.config.alert_threshold:
                    alert_key = (
                        f"{route.origin}-{route.destination}-"
                        f"{depart_date.isoformat()}-{return_date.isoformat()}"
                    )
                    if self.storage.should_fire_alert(
                        alert_key,
                        cooldown_minutes=self.config.alert_cooldown_minutes,
                    ):
                        self.notifier.notify(
                            AlertMessage(
                                quote=quote,
                                threshold=self.config.alert_threshold,
                                historical_low=historical_low,
                            )
                        )
                        self.storage.record_alert(alert_key)

                print(
                    "[QUOTE] "
                    f"{origin}->{self.config.destination} "
                    f"{depart_date}/{return_date} "
                    f"dep={quote.depart_time or 'N/A'} "
                    f"arr={quote.arrive_time or 'N/A'} "
                    f"🔥PRICE={quote.total_price:.2f} {quote.currency}🔥 "
                    f"(src={quote.source_price:.2f} {quote.source_currency}, "
                    f"fx={quote.exchange_rate:.4f}) "
                    f"position={quote.price_position} "
                    f"hist(min={historical_stats.get('min')}, "
                    f"max={historical_stats.get('max')}, "
                    f"avg={historical_stats.get('avg')})"
                , flush=True)

        print("[RUN] run-once 执行完成", flush=True)

    def run_thailand_cheapest(self) -> None:
        depart_date, return_date = self._get_active_date_pair()
        print(
            "[TH] 开始检索泰国最低价 "
            f"date={depart_date}/{return_date}",
            flush=True,
        )

        best_item: dict[str, str | float | None] | None = None

        for origin in self.config.origins:
            for destination in self.config.thailand_destinations:
                if origin == destination:
                    continue
                print(
                    "[TH] 查询 "
                    f"{origin}->{destination} {depart_date}/{return_date}",
                    flush=True,
                )

                source_price = self.provider.get_roundtrip_price(
                    origin=origin,
                    destination=destination,
                    depart_date=depart_date,
                    return_date=return_date,
                    currency=self.config.currency,
                )
                if source_price is None:
                    print(
                        "[TH] 未取到价格 "
                        f"{origin}->{destination}",
                        flush=True,
                    )
                    continue

                source_currency = (
                    getattr(self.provider, "quote_currency", None)
                    or self.config.currency
                )
                converted_price = source_price
                fx_rate = 1.0
                if source_currency != self.config.currency:
                    converted_price, fx_rate = self.fx_converter.convert(
                        amount=source_price,
                        base=source_currency,
                        target=self.config.currency,
                    )

                meta = self.provider.get_last_quote_meta()
                depart_time = meta.get("depart_time")
                if not self._is_depart_time_allowed(
                    depart_time if isinstance(depart_time, str) else None
                ):
                    print(
                        "[TH] 跳过（不满足最早起飞时间） "
                        f"{origin}->{destination} dep={depart_time}",
                        flush=True,
                    )
                    continue

                print(
                    "[TH-QUOTE] "
                    f"{origin}->{destination} "
                    f"dep={meta.get('depart_time') or 'N/A'} "
                    f"arr={meta.get('arrive_time') or 'N/A'} "
                    f"🔥PRICE={converted_price:.2f} {self.config.currency}🔥 "
                    f"(src={source_price:.2f} {source_currency}, fx={fx_rate:.4f})",
                    flush=True,
                )

                if (
                    best_item is None
                    or converted_price < float(best_item["converted_price"])
                ):
                    best_item = {
                        "origin": origin,
                        "destination": destination,
                        "depart_time": (
                            meta.get("depart_time")
                            if isinstance(meta.get("depart_time"), str)
                            else None
                        ),
                        "arrive_time": (
                            meta.get("arrive_time")
                            if isinstance(meta.get("arrive_time"), str)
                            else None
                        ),
                        "converted_price": converted_price,
                        "source_price": source_price,
                        "source_currency": source_currency,
                        "fx_rate": fx_rate,
                    }

        if not best_item:
            print("[TH] 未检索到可用价格", flush=True)
            return

        print(
            "[TH-CHEAPEST] "
            f"{best_item['origin']}->{best_item['destination']} "
            f"{depart_date}/{return_date} "
            f"dep={best_item['depart_time'] or 'N/A'} "
            f"arr={best_item['arrive_time'] or 'N/A'} "
            f"🔥PRICE={float(best_item['converted_price']):.2f} {self.config.currency}🔥 "
            f"(src={float(best_item['source_price']):.2f} "
            f"{best_item['source_currency']}, "
            f"fx={float(best_item['fx_rate']):.4f})",
            flush=True,
        )

    def _scan_cheapest_for_destinations(
        self,
        destinations: list[str],
    ) -> tuple[
        date,
        date,
        dict[str, str | float | None] | None,
        dict[str, str | float | None] | None,
    ]:
        depart_date, return_date = self._get_active_date_pair()
        best_item: dict[str, str | float | None] | None = None
        best_direct_item: dict[str, str | float | None] | None = None
        best_transfer_within_limit: dict[str, str | float | None] | None = None
        best_transfer_shortest: dict[str, str | float | None] | None = None
        best_transfer_shortest_score: tuple[float, float] | None = None

        provider_set_verbose = getattr(self.provider, "set_verbose", None)
        if callable(provider_set_verbose):
            provider_set_verbose(False)

        try:
            for origin in self.config.origins:
                for destination in destinations:
                    if origin == destination:
                        continue
                    source_price = self.provider.get_roundtrip_price(
                        origin=origin,
                        destination=destination,
                        depart_date=depart_date,
                        return_date=return_date,
                        currency=self.config.currency,
                    )
                    if source_price is None:
                        continue

                    source_currency = (
                        getattr(self.provider, "quote_currency", None)
                        or self.config.currency
                    )
                    converted_price = source_price
                    fx_rate = 1.0
                    if source_currency != self.config.currency:
                        converted_price, fx_rate = self.fx_converter.convert(
                            amount=source_price,
                            base=source_currency,
                            target=self.config.currency,
                        )

                    meta = self.provider.get_last_quote_meta()
                    depart_time = (
                        meta.get("depart_time")
                        if isinstance(meta.get("depart_time"), str)
                        else None
                    )
                    if not self._is_depart_time_allowed(depart_time):
                        continue

                    candidate = {
                        "origin": origin,
                        "destination": destination,
                        "depart_time": depart_time,
                        "arrive_time": (
                            meta.get("arrive_time")
                            if isinstance(meta.get("arrive_time"), str)
                            else None
                        ),
                        "return_depart_time": (
                            meta.get("return_depart_time")
                            if isinstance(meta.get("return_depart_time"), str)
                            else None
                        ),
                        "return_arrive_time": (
                            meta.get("return_arrive_time")
                            if isinstance(meta.get("return_arrive_time"), str)
                            else None
                        ),
                        "outbound_journey": (
                            meta.get("outbound_journey")
                            if isinstance(meta.get("outbound_journey"), str)
                            else None
                        ),
                        "return_journey": (
                            meta.get("return_journey")
                            if isinstance(meta.get("return_journey"), str)
                            else None
                        ),
                        "outbound_stopovers": (
                            meta.get("outbound_stopovers")
                            if isinstance(meta.get("outbound_stopovers"), str)
                            else None
                        ),
                        "return_stopovers": (
                            meta.get("return_stopovers")
                            if isinstance(meta.get("return_stopovers"), str)
                            else None
                        ),
                        "outbound_stopover_details": (
                            meta.get("outbound_stopover_details")
                            if isinstance(
                                meta.get("outbound_stopover_details"),
                                str,
                            )
                            else None
                        ),
                        "return_stopover_details": (
                            meta.get("return_stopover_details")
                            if isinstance(
                                meta.get("return_stopover_details"),
                                str,
                            )
                            else None
                        ),
                        "converted_price": converted_price,
                        "source_price": source_price,
                        "source_currency": source_currency,
                        "fx_rate": fx_rate,
                    }

                    if self._candidate_is_direct(candidate):
                        if (
                            best_direct_item is None
                            or converted_price
                            < float(best_direct_item["converted_price"])
                        ):
                            best_direct_item = candidate
                        continue

                    max_layover = self._candidate_max_layover_hours(candidate)
                    if max_layover is not None and max_layover <= 3.0:
                        if (
                            best_transfer_within_limit is None
                            or converted_price
                            < float(best_transfer_within_limit["converted_price"])
                        ):
                            best_transfer_within_limit = candidate

                    layover_score = max_layover if max_layover is not None else 999.0
                    score = (layover_score, float(converted_price))
                    if (
                        best_transfer_shortest_score is None
                        or score < best_transfer_shortest_score
                    ):
                        best_transfer_shortest_score = score
                        best_transfer_shortest = candidate
        finally:
            if callable(provider_set_verbose):
                provider_set_verbose(True)

        if best_direct_item is not None:
            best_item = best_direct_item
        elif best_transfer_within_limit is not None:
            best_item = best_transfer_within_limit
        else:
            best_item = best_transfer_shortest

        return depart_date, return_date, best_item, best_direct_item

    def run_best_deals_summary(self) -> None:
        def format_deal_line(
            prefix: str,
            deal_item: dict[str, str | float | None],
            depart_date_value: date,
            return_date_value: date,
        ) -> str:
            base = (
                f"{prefix} "
                f"{deal_item['origin']}->{deal_item['destination']} "
                f"{depart_date_value}/{return_date_value} "
                f"go={deal_item['depart_time'] or 'N/A'}->{deal_item['arrive_time'] or 'N/A'} "
                f"back={deal_item['return_depart_time'] or 'N/A'}->{deal_item['return_arrive_time'] or 'N/A'} "
                f"🔥PRICE={float(deal_item['converted_price']):.2f} {self.config.currency}🔥 "
                f"(src={float(deal_item['source_price']):.2f} {deal_item['source_currency']}, "
                f"fx={float(deal_item['fx_rate']):.4f})"
            )
            if self._candidate_is_direct(deal_item):
                return base + " direct=Y"
            return (
                base
                + f" back_route={deal_item['return_journey'] or 'N/A'}"
                + f" back_stop={deal_item['return_stopovers'] or 'N/A'}"
                + f" back_stop_detail={deal_item['return_stopover_details'] or 'N/A'}"
            )

        def build_feishu_deal_block(
            title: str,
            deal_item: dict[str, str | float | None] | None,
            direct_item: dict[str, str | float | None] | None,
        ) -> list[str]:
            if deal_item is None:
                return [title, "- 状态: 无可用价格"]

            lines = [
                title,
                f"- 航线: {deal_item['origin']} -> {deal_item['destination']}",
                (
                    "- 去程: "
                    f"{deal_item['depart_time'] or 'N/A'} "
                    f"-> {deal_item['arrive_time'] or 'N/A'}"
                ),
                (
                    "- 返程: "
                    f"{deal_item['return_depart_time'] or 'N/A'} "
                    f"-> {deal_item['return_arrive_time'] or 'N/A'}"
                ),
                (
                    "- 价格: "
                    f"{float(deal_item['converted_price']):.2f} "
                    f"{self.config.currency} "
                    f"(原价 {float(deal_item['source_price']):.2f} "
                    f"{deal_item['source_currency']}, "
                    f"汇率 {float(deal_item['fx_rate']):.4f})"
                ),
            ]

            if self._candidate_is_direct(deal_item):
                lines.append("- 机型类型: 直飞")
            else:
                lines.extend(
                    [
                        f"- 返程路由: {deal_item['return_journey'] or 'N/A'}",
                        f"- 返程中转: {deal_item['return_stopovers'] or 'N/A'}",
                        (
                            "- 返程中转明细: "
                            f"{deal_item['return_stopover_details'] or 'N/A'}"
                        ),
                    ]
                )
                if direct_item is not None:
                    lines.extend(
                        [
                            "- 备选最优直飞:",
                            (
                                f"  {direct_item['origin']}->{direct_item['destination']} "
                                f"go={direct_item['depart_time'] or 'N/A'}->{direct_item['arrive_time'] or 'N/A'} "
                                f"back={direct_item['return_depart_time'] or 'N/A'}->{direct_item['return_arrive_time'] or 'N/A'} "
                                f"price={float(direct_item['converted_price']):.2f} {self.config.currency}"
                            ),
                        ]
                    )

            return lines

        (
            depart_date,
            return_date,
            pqc_best,
            pqc_best_direct,
        ) = self._scan_cheapest_for_destinations(
            [self.config.destination]
        )
        (
            _,
            _,
            thailand_best,
            thailand_best_direct,
        ) = self._scan_cheapest_for_destinations(
            self.config.thailand_destinations
        )

        summary_lines: list[str] = [
            f"[机票汇总] {depart_date}/{return_date}",
        ]

        if pqc_best is None:
            line = f"[DEAL-PQC] {depart_date}/{return_date} 无可用价格"
            print(line, flush=True)
            summary_lines.append(line)
        else:
            line = format_deal_line(
                "[DEAL-PQC]",
                pqc_best,
                depart_date,
                return_date,
            )
            print(line, flush=True)
            summary_lines.append(line)
            if (
                not self._candidate_is_direct(pqc_best)
                and pqc_best_direct is not None
            ):
                direct_line = format_deal_line(
                    "[DEAL-PQC-DIRECT]",
                    pqc_best_direct,
                    depart_date,
                    return_date,
                )
                print(direct_line, flush=True)
                summary_lines.append(direct_line)

        if thailand_best is None:
            line = f"[DEAL-TH] {depart_date}/{return_date} 无可用价格"
            print(line, flush=True)
            summary_lines.append(line)
        else:
            line = format_deal_line(
                "[DEAL-TH]",
                thailand_best,
                depart_date,
                return_date,
            )
            print(line, flush=True)
            summary_lines.append(line)
            if (
                not self._candidate_is_direct(thailand_best)
                and thailand_best_direct is not None
            ):
                direct_line = format_deal_line(
                    "[DEAL-TH-DIRECT]",
                    thailand_best_direct,
                    depart_date,
                    return_date,
                )
                print(direct_line, flush=True)
                summary_lines.append(direct_line)

        if self.config.feishu_webhook_url:
            try:
                feishu_lines: list[str] = [
                    "【机票汇总】",
                    f"日期: {depart_date} / {return_date}",
                    "",
                    *build_feishu_deal_block(
                        "【PQC 最低价】",
                        pqc_best,
                        pqc_best_direct,
                    ),
                    "",
                    *build_feishu_deal_block(
                        "【泰国最低价】",
                        thailand_best,
                        thailand_best_direct,
                    ),
                ]
                feishu_notifier = FeishuNotifier(
                    webhook_url=self.config.feishu_webhook_url,
                    secret=self.config.feishu_secret,
                )
                feishu_notifier.send_text("\n".join(feishu_lines))
                print("[FEISHU] 汇总推送成功", flush=True)
            except Exception as error:
                print(f"[FEISHU] 汇总推送失败: {error}", flush=True)

    def run_loop(self) -> None:
        print(
            f"开始循环监控: 每 {self.config.interval_minutes} 分钟执行一次"
        , flush=True)
        while True:
            print("\n==== 新一轮监控开始 ====", flush=True)
            self.run_once()
            print("==== 本轮结束 ====", flush=True)
            time.sleep(self.config.interval_minutes * 60)
