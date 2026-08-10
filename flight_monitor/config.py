from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

from flight_monitor.date_utils import get_festival_span


@dataclass(frozen=True)
class SearchTask:
    """单个搜索任务定义 — 对应 config.yaml tasks 列表中的每一项。"""

    name: str
    origin: str
    destination: str
    depart_date: date
    return_date: date
    window_days: int = 1
    min_trip_days: int | None = None
    no_thailand: bool = False
    max_retries: int | None = None
    timeout_seconds: int | None = None
    group: str = "daily"


@dataclass(frozen=True)
class AppConfig:
    provider: str
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
    bark_device_key: str | None
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
    festival: str
    trip_scrape_max_retries: int = 3
    tasks: list[SearchTask] = field(default_factory=list)


def _parse_tasks(raw: list[dict]) -> list[SearchTask]:
    tasks: list[SearchTask] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        tasks.append(SearchTask(
            name=str(item["name"]),
            origin=str(item["origin"]).upper(),
            destination=str(item["destination"]).upper(),
            depart_date=date.fromisoformat(str(item["depart_date"])),
            return_date=date.fromisoformat(str(item["return_date"])),
            window_days=int(item.get("window_days", 1)),
            min_trip_days=(
                int(item["min_trip_days"])
                if item.get("min_trip_days") is not None
                else None
            ),
            no_thailand=bool(item.get("no_thailand", False)),
            max_retries=(
                int(item["max_retries"])
                if item.get("max_retries") is not None
                else None
            ),
            timeout_seconds=(
                int(item["timeout_seconds"])
                if item.get("timeout_seconds") is not None
                else None
            ),
            group=str(item.get("group", "daily")).strip().lower(),
        ))
    return tasks


def create_default_config(
    year: int | None = None,
    festival: str = "none",
) -> AppConfig:
    monitor_year = year or date.today().year
    if festival != "none":
        holiday_start, holiday_end = get_festival_span(festival, monitor_year)
        start = holiday_start - timedelta(days=5)
        end = holiday_end + timedelta(days=5)
    else:
        today = date.today()
        start = today + timedelta(days=1)
        end = today + timedelta(days=10)
    return AppConfig(
        provider="mock",
        trip_scrape_timeout_seconds=60,
        trip_scrape_max_retries=3,
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
        bark_device_key=None,
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
        festival=festival,
        tasks=[],
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
        trip_scrape_timeout_seconds=int(
            payload.get("trip_scrape_timeout_seconds", 60)
        ),
        trip_scrape_max_retries=int(
            payload.get("trip_scrape_max_retries", 3)
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
        bark_device_key=payload.get("bark_device_key"),
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
        festival=payload.get("festival", "dragon_boat"),
        tasks=_parse_tasks(payload.get("tasks", [])),
    )


def save_config(config: AppConfig, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": config.provider,
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
        "bark_device_key": config.bark_device_key,
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
        "festival": config.festival,
        "tasks": [
            {
                "name": t.name,
                "origin": t.origin,
                "destination": t.destination,
                "depart_date": t.depart_date.isoformat(),
                "return_date": t.return_date.isoformat(),
                "window_days": t.window_days,
                "min_trip_days": t.min_trip_days,
                "no_thailand": t.no_thailand,
            }
            for t in config.tasks
        ],
    }
    with output_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(payload, file, allow_unicode=True, sort_keys=False)
