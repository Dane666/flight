from dataclasses import dataclass
from email.message import EmailMessage
import smtplib

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
