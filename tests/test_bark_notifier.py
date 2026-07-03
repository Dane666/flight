"""自测：Bark 通知器替代飞书通知器。"""

import json
import os
from datetime import date, datetime
from unittest.mock import patch, MagicMock

import pytest

from flight_monitor.config import (
    AppConfig,
    create_default_config,
    load_config,
    save_config,
)
from flight_monitor.models import PriceQuote, Route
from flight_monitor.notifier import (
    BarkNotifier,
    ConsoleNotifier,
    AlertMessage,
    BARK_URL,
)


class TestAppConfig:
    def test_default_config_no_feishu_fields(self):
        cfg = create_default_config()
        assert not hasattr(cfg, "feishu_webhook_url")
        assert not hasattr(cfg, "feishu_secret")

    def test_default_config_has_bark_field(self):
        cfg = create_default_config()
        assert cfg.bark_device_key is None

    def test_save_and_load_roundtrip(self, tmp_path):
        cfg = create_default_config()
        cfg_path = tmp_path / "config.yaml"
        save_config(cfg, cfg_path)
        reloaded = load_config(cfg_path)
        assert reloaded.bark_device_key == cfg.bark_device_key


class TestBarkNotifier:
    def test_notify_sends_bark(self):
        notifier = BarkNotifier(device_key="test_key_123")
        with patch("flight_monitor.notifier.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp

            quote = PriceQuote(
                route=Route(origin="HKG", destination="PQC"),
                depart_date=date(2026, 11, 6),
                return_date=date(2026, 11, 9),
                total_price=1800.0,
                currency="CNY",
                provider="trip_scrape",
                observed_at=datetime.now(),
            )
            notifier.notify(
                AlertMessage(quote=quote, threshold=2200.0, historical_low=1500.0)
            )

            mock_post.assert_called_once()
            args = mock_post.call_args
            assert args[0][0] == BARK_URL
            payload = args[1]["json"]
            assert payload["device_key"] == "test_key_123"
            assert payload["group"] == "Flight"
            assert "HKG->PQC" in payload["body"]

    def test_send_text_splits_title_and_body(self):
        notifier = BarkNotifier(device_key="key")
        with patch("flight_monitor.notifier.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            notifier.send_text("【机票汇总】\n日期: 2026-01-01\n内容行")

            payload = mock_post.call_args[1]["json"]
            assert payload["title"] == "【机票汇总】"
            assert "日期: 2026-01-01" in payload["body"]

    def test_send_text_single_line(self):
        notifier = BarkNotifier(device_key="key")
        with patch("flight_monitor.notifier.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            notifier.send_text("只有一行")
            payload = mock_post.call_args[1]["json"]
            assert payload["title"] == "只有一行"

    def test_empty_device_key_skips(self):
        notifier = BarkNotifier(device_key=None)
        with patch("flight_monitor.notifier.requests.post") as mock_post:
            notifier.send_text("test")
            mock_post.assert_not_called()

    def test_device_key_url_format(self):
        notifier = BarkNotifier(device_key="https://api.day.app/abcd1234/")
        with patch("flight_monitor.notifier.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            notifier.send_text("test")
            payload = mock_post.call_args[1]["json"]
            assert payload["device_key"] == "abcd1234"

    def test_content_truncation(self):
        notifier = BarkNotifier(device_key="key")
        with patch("flight_monitor.notifier.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            notifier.send_text("title\n" + "x" * 5000)
            payload = mock_post.call_args[1]["json"]
            assert len(payload["body"]) <= 3800

    def test_bark_request_failure_no_raise(self):
        notifier = BarkNotifier(device_key="key")
        with patch("flight_monitor.notifier.requests.post") as mock_post:
            mock_post.side_effect = Exception("Connection failed")
            notifier.send_text("test")  # should not raise

    def test_http_error_handled(self):
        notifier = BarkNotifier(device_key="key")
        with patch("flight_monitor.notifier.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.text = "Internal Server Error"
            mock_post.return_value = mock_resp
            notifier.send_text("test")  # should not raise

    def test_os_environ_fallback(self):
        with patch.dict(os.environ, {"BARK_DEVICE_KEY": "env_key_xyz"}):
            notifier = BarkNotifier()
            assert notifier.device_key == "env_key_xyz"


class TestExistingNotifiers:
    def test_console_notifier_still_works(self):
        notifier = ConsoleNotifier()
        quote = PriceQuote(
            route=Route(origin="CAN", destination="BKK"),
            depart_date=date(2026, 1, 1),
            return_date=date(2026, 1, 5),
            total_price=2100.0,
            currency="CNY",
            provider="mock",
            observed_at=datetime.now(),
        )
        with patch("builtins.print") as mock_print:
            notifier.notify(
                AlertMessage(quote=quote, threshold=2200.0, historical_low=None)
            )
            printed = " ".join(
                str(call.args[0]) for call in mock_print.call_args_list
            )
            assert "[ALERT]" in printed
            assert "CAN->BKK" in printed
