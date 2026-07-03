from dataclasses import dataclass
from email.message import EmailMessage
import os
import smtplib

import requests

from flight_monitor.models import PriceQuote

BARK_URL = "https://api.day.app/push"


@dataclass(frozen=True)
class AlertMessage:
    quote: PriceQuote
    threshold: float
    historical_low: float | None


class ConsoleNotifier:
    def notify(self, message: AlertMessage) -> None:
        quote = message.quote
        low_text = (
            f"{message.historical_low:.2f}"
            if message.historical_low is not None
            else "N/A"
        )
        print(
            "[ALERT] "
            f"{quote.route.origin}->{quote.route.destination} "
            f"{quote.depart_date}~{quote.return_date} "
            f"price={quote.total_price:.2f} {quote.currency} "
            f"threshold={message.threshold:.2f} "
            f"historical_low={low_text}"
        )


class EmailNotifier:
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_username: str,
        smtp_password: str,
        email_from: str,
        email_to: list[str],
        smtp_use_tls: bool = True,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.email_from = email_from
        self.email_to = email_to
        self.smtp_use_tls = smtp_use_tls

    def notify(self, message: AlertMessage) -> None:
        quote = message.quote
        low_text = (
            f"{message.historical_low:.2f}"
            if message.historical_low is not None
            else "N/A"
        )
        subject = (
            f"[机票降价提醒] {quote.route.origin}->{quote.route.destination} "
            f"{quote.depart_date}~{quote.return_date}"
        )
        body = (
            f"航线: {quote.route.origin}->{quote.route.destination}\n"
            f"日期: {quote.depart_date} ~ {quote.return_date}\n"
            f"当前价格: {quote.total_price:.2f} {quote.currency}\n"
            f"阈值: {message.threshold:.2f}\n"
            f"历史低价: {low_text}\n"
            f"数据源: {quote.provider}\n"
            f"抓取时间: {quote.observed_at.isoformat()}\n"
        )

        email = EmailMessage()
        email["Subject"] = subject
        email["From"] = self.email_from
        email["To"] = ", ".join(self.email_to)
        email.set_content(body)

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20) as server:
            if self.smtp_use_tls:
                server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.send_message(email)

        print(
            "[ALERT-EMAIL-SENT] "
            f"{quote.route.origin}->{quote.route.destination} "
            f"{quote.depart_date}/{quote.return_date}"
        )


class BarkNotifier:
    def __init__(self, device_key: str | None = None) -> None:
        self.device_key = device_key or os.environ.get("BARK_DEVICE_KEY", "")

    def _send_bark(self, title: str, content: str) -> None:
        if not self.device_key:
            print("[BARK] BARK_DEVICE_KEY 未配置，跳过推送", flush=True)
            return

        key = self.device_key
        if key.startswith("http"):
            parts = key.rstrip("/").split("/")
            key = parts[-1] if parts[-1] else (parts[-2] if len(parts) > 1 else key)

        body = content[:3800]
        payload = {
            "device_key": key,
            "title": title,
            "body": body,
            "group": "Flight",
        }

        try:
            response = requests.post(BARK_URL, json=payload, timeout=10)
            if response.status_code == 200:
                print("[BARK] 推送成功", flush=True)
            else:
                print(f"[BARK] 推送失败: {response.text}", flush=True)
        except Exception as error:
            print(f"[BARK] 推送错误: {error}", flush=True)

    def send_text(self, text: str) -> None:
        lines = text.strip().split("\n", 1)
        title = lines[0] if lines else "机票通知"
        content = lines[1] if len(lines) > 1 else ""
        self._send_bark(title, content)

    def notify(self, message: AlertMessage) -> None:
        quote = message.quote
        low_text = (
            f"{message.historical_low:.2f}"
            if message.historical_low is not None
            else "N/A"
        )
        title = f"机票提醒 {quote.route.origin}->{quote.route.destination}"
        content = (
            f"航线: {quote.route.origin}->{quote.route.destination}\n"
            f"日期: {quote.depart_date} ~ {quote.return_date}\n"
            f"价格: {quote.total_price:.2f} {quote.currency}\n"
            f"阈值: {message.threshold:.2f}\n"
            f"历史低价: {low_text}"
        )
        self._send_bark(title, content)
        print(
            "[ALERT-BARK-SENT] "
            f"{quote.route.origin}->{quote.route.destination} "
            f"{quote.depart_date}/{quote.return_date}"
        )
