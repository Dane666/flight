from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from flight_monitor.date_utils import around_day_window, dragon_boat_date


@dataclass(frozen=True)
class AppConfig:
    provider: str
    serpapi_api_key: str | None
    kiwi_api_key: str | None
    amadeus_client_id: str | None
    amadeus_client_secret: str | None
    amadeus_base_url: str
    google_flights_hl: str
    google_flights_gl: str
    trip_scrape_timeout_seconds: int
    currency: str
    interval_minutes: int
    alert_threshold: float
    alert_cooldown_minutes: int
    notifier: str
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_use_tls: bool
    email_from: str | None
    email_to: list[str]
    feishu_webhook_url: str | None
    feishu_secret: str | None
    db_path: str
    origins: list[str]
    destination: str
    thailand_destinations: list[str]
    window_start: date
    window_end: date
    fixed_depart_date: date | None
    fixed_return_date: date | None
    min_depart_time: str | None
    min_trip_days: int
    max_trip_span_days: int
    max_leave_workdays: int


def create_default_config(year: int | None = None) -> AppConfig:
    monitor_year = year or date.today().year
    dragon_boat = dragon_boat_date(monitor_year)
    start, end = around_day_window(dragon_boat, days=5)
    return AppConfig(
        provider="mock",
        serpapi_api_key=None,
        kiwi_api_key=None,
        amadeus_client_id=None,
        amadeus_client_secret=None,
        amadeus_base_url="https://test.api.amadeus.com",
        google_flights_hl="en",
        google_flights_gl="hk",
        trip_scrape_timeout_seconds=60,
        currency="CNY",
        interval_minutes=30,
        alert_threshold=2200,
        alert_cooldown_minutes=180,
        notifier="console",
        smtp_host=None,
        smtp_port=587,
        smtp_username=None,
        smtp_password=None,
        smtp_use_tls=True,
        email_from=None,
        email_to=[],
        feishu_webhook_url=None,
        feishu_secret=None,
        db_path="data/flight_prices.db",
        origins=["CAN", "SZX", "HKG"],
        destination="PQC",
        thailand_destinations=["BKK", "DMK", "HKT", "CNX", "KBV"],
        window_start=start,
        window_end=end,
        fixed_depart_date=None,
        fixed_return_date=None,
        min_depart_time=None,
        min_trip_days=4,
        max_trip_span_days=6,
        max_leave_workdays=3,
    )


def load_config(config_path: Path) -> AppConfig:
    with config_path.open("r", encoding="utf-8") as file:
        payload = yaml.safe_load(file)

    if isinstance(payload, str):
        payload = yaml.safe_load(payload)

    if not isinstance(payload, dict):
        raise ValueError(
            "配置文件格式错误：应为 YAML 对象（key-value），"
            f"实际类型为 {type(payload).__name__}"
        )

    return AppConfig(
        provider=payload.get("provider", "mock"),
        serpapi_api_key=payload.get("serpapi_api_key"),
        kiwi_api_key=payload.get("kiwi_api_key"),
        amadeus_client_id=payload.get("amadeus_client_id"),
        amadeus_client_secret=payload.get("amadeus_client_secret"),
        amadeus_base_url=payload.get(
            "amadeus_base_url", "https://test.api.amadeus.com"
        ),
        google_flights_hl=payload.get("google_flights_hl", "en"),
        google_flights_gl=payload.get("google_flights_gl", "hk"),
        trip_scrape_timeout_seconds=int(
            payload.get("trip_scrape_timeout_seconds", 60)
        ),
        currency=payload["currency"],
        interval_minutes=int(payload["interval_minutes"]),
        alert_threshold=float(payload["alert_threshold"]),
        alert_cooldown_minutes=int(payload["alert_cooldown_minutes"]),
        notifier=payload.get("notifier", "console"),
        smtp_host=payload.get("smtp_host"),
        smtp_port=int(payload.get("smtp_port", 587)),
        smtp_username=payload.get("smtp_username"),
        smtp_password=payload.get("smtp_password"),
        smtp_use_tls=bool(payload.get("smtp_use_tls", True)),
        email_from=payload.get("email_from"),
        email_to=list(payload.get("email_to", [])),
        feishu_webhook_url=payload.get("feishu_webhook_url"),
        feishu_secret=payload.get("feishu_secret"),
        db_path=payload["db_path"],
        origins=list(payload["origins"]),
        destination=payload["destination"],
        thailand_destinations=list(
            payload.get(
                "thailand_destinations",
                ["BKK", "DMK", "HKT", "CNX", "KBV"],
            )
        ),
        window_start=date.fromisoformat(payload["window_start"]),
        window_end=date.fromisoformat(payload["window_end"]),
        fixed_depart_date=(
            date.fromisoformat(payload["fixed_depart_date"])
            if payload.get("fixed_depart_date")
            else None
        ),
        fixed_return_date=(
            date.fromisoformat(payload["fixed_return_date"])
            if payload.get("fixed_return_date")
            else None
        ),
        min_depart_time=payload.get("min_depart_time"),
        min_trip_days=int(payload.get("min_trip_days", 4)),
        max_trip_span_days=int(payload.get("max_trip_span_days", 6)),
        max_leave_workdays=int(payload.get("max_leave_workdays", 3)),
    )


def save_config(config: AppConfig, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": config.provider,
        "serpapi_api_key": config.serpapi_api_key,
        "kiwi_api_key": config.kiwi_api_key,
        "amadeus_client_id": config.amadeus_client_id,
        "amadeus_client_secret": config.amadeus_client_secret,
        "amadeus_base_url": config.amadeus_base_url,
        "google_flights_hl": config.google_flights_hl,
        "google_flights_gl": config.google_flights_gl,
        "trip_scrape_timeout_seconds": config.trip_scrape_timeout_seconds,
        "currency": config.currency,
        "interval_minutes": config.interval_minutes,
        "alert_threshold": config.alert_threshold,
        "alert_cooldown_minutes": config.alert_cooldown_minutes,
        "notifier": config.notifier,
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
        "smtp_username": config.smtp_username,
        "smtp_password": config.smtp_password,
        "smtp_use_tls": config.smtp_use_tls,
        "email_from": config.email_from,
        "email_to": config.email_to,
        "feishu_webhook_url": config.feishu_webhook_url,
        "feishu_secret": config.feishu_secret,
        "db_path": config.db_path,
        "origins": config.origins,
        "destination": config.destination,
        "thailand_destinations": config.thailand_destinations,
        "window_start": config.window_start.isoformat(),
        "window_end": config.window_end.isoformat(),
        "fixed_depart_date": (
            config.fixed_depart_date.isoformat()
            if config.fixed_depart_date
            else None
        ),
        "fixed_return_date": (
            config.fixed_return_date.isoformat()
            if config.fixed_return_date
            else None
        ),
        "min_depart_time": config.min_depart_time,
        "min_trip_days": config.min_trip_days,
        "max_trip_span_days": config.max_trip_span_days,
        "max_leave_workdays": config.max_leave_workdays,
    }
    with output_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(payload, file, allow_unicode=True, sort_keys=False)
