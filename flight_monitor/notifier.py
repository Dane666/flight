from dataclasses import dataclass
from email.message import EmailMessage
import base64
import hashlib
import hmac
import json
import time
import smtplib

import requests

from flight_monitor.models import PriceQuote


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


class FeishuNotifier:
    def __init__(
        self,
        webhook_url: str,
        secret: str | None = None,
    ) -> None:
        self.webhook_url = webhook_url
        self.secret = secret

    def _build_sign_headers(self) -> dict[str, str]:
        if not self.secret:
            return {}

        timestamp = str(int(time.time()))
        sign_str = f"{timestamp}\n{self.secret}".encode("utf-8")
        digest = hmac.new(
            self.secret.encode("utf-8"),
            sign_str,
            digestmod=hashlib.sha256,
        ).digest()
        sign = base64.b64encode(digest).decode("utf-8")
        return {"timestamp": timestamp, "sign": sign}

    def _is_flow_webhook(self) -> bool:
        return "feishu.cn/flow/api/trigger-webhook/" in self.webhook_url

    def _flatten_text_for_flow(self, text: str) -> str:
        chunks = [line.strip() for line in text.splitlines() if line.strip()]
        if not chunks:
            return text
        return "  |  ".join(chunks)

    def send_text(self, text: str) -> None:
        if self._is_flow_webhook():
            flow_text = self._flatten_text_for_flow(text)
            payload = {
                "text": flow_text,
            }
        else:
            payload = {
                "msg_type": "text",
                "content": {"text": text},
            }
        payload.update(self._build_sign_headers())

        response = requests.post(
            self.webhook_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=15,
        )
        response.raise_for_status()

    def notify(self, message: AlertMessage) -> None:
        quote = message.quote
        low_text = (
            f"{message.historical_low:.2f}"
            if message.historical_low is not None
            else "N/A"
        )
        text = (
            "[机票提醒]\n"
            f"航线: {quote.route.origin}->{quote.route.destination}\n"
            f"日期: {quote.depart_date} ~ {quote.return_date}\n"
            f"价格: {quote.total_price:.2f} {quote.currency}\n"
            f"阈值: {message.threshold:.2f}\n"
            f"历史低价: {low_text}"
        )
        self.send_text(text)
        print(
            "[ALERT-FEISHU-SENT] "
            f"{quote.route.origin}->{quote.route.destination} "
            f"{quote.depart_date}/{quote.return_date}"
        )
