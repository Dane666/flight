from datetime import date
from pathlib import Path

import pytest

from flight_monitor.config import (
    AppConfig,
    SearchTask,
    create_default_config,
    load_config,
    save_config,
)
from flight_monitor.monitor import _meta_str


def test_real_config_loads_tasks():
    """回归保护：仓库中的 config.yaml 必须能正确解析 tasks。"""
    config = load_config(Path("config.yaml"))
    assert config.provider == "trip_scrape"
    assert len(config.tasks) >= 1
    for task in config.tasks:
        assert isinstance(task, SearchTask)
        assert task.depart_date < task.return_date
        assert task.origin and task.destination


def test_search_task_fields():
    task = SearchTask(
        name="t1",
        origin="CAN",
        destination="PQC",
        depart_date=date(2026, 1, 1),
        return_date=date(2026, 1, 5),
        window_days=1,
        min_trip_days=4,
        no_thailand=True,
    )
    assert task.name == "t1"
    assert task.origin == "CAN"
    assert task.window_days == 1
    assert task.no_thailand is True


def test_config_save_load_roundtrip_with_tasks(tmp_path):
    cfg = create_default_config(festival="dragon_boat")
    tasks = [
        SearchTask(
            name="demo",
            origin="HKG",
            destination="PQC",
            depart_date=date(2026, 10, 1),
            return_date=date(2026, 10, 5),
            window_days=2,
            min_trip_days=4,
            no_thailand=False,
        )
    ]
    cfg = cfg.__class__(**{**cfg.__dict__, "tasks": tasks})

    out = tmp_path / "cfg.yaml"
    save_config(cfg, out)
    loaded = load_config(out)

    assert len(loaded.tasks) == 1
    t = loaded.tasks[0]
    assert t.name == "demo"
    assert t.origin == "HKG"
    assert t.destination == "PQC"
    assert t.depart_date == date(2026, 10, 1)
    assert t.return_date == date(2026, 10, 5)
    assert t.window_days == 2
    assert t.min_trip_days == 4
    assert t.no_thailand is False


def test_meta_str_helper():
    meta = {
        "depart_time": "08:30",
        "price": 1234,
        "missing": None,
    }
    assert _meta_str(meta, "depart_time") == "08:30"
    assert _meta_str(meta, "missing") is None
    assert _meta_str(meta, "price") is None  # non-str ignored
    assert _meta_str(meta, "not_present") is None


def test_deprecated_provider_fields_removed():
    """回归保护：已弃用的 API key 字段不应再出现在 AppConfig 中。"""
    fields = set(AppConfig.__dataclass_fields__.keys())
    for removed in (
        "serpapi_api_key",
        "kiwi_api_key",
        "amadeus_client_id",
        "amadeus_client_secret",
        "amadeus_base_url",
        "google_flights_hl",
        "google_flights_gl",
    ):
        assert removed not in fields
