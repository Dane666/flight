import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from flight_monitor.models import PriceQuote, Route


class PriceStorage:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS price_quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    origin TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    depart_date TEXT NOT NULL,
                    return_date TEXT NOT NULL,
                    total_price REAL NOT NULL,
                    currency TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                )
                """
            )
            existing_columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(price_quotes)")
            }
            if "source_price" not in existing_columns:
                conn.execute(
                    "ALTER TABLE price_quotes ADD COLUMN source_price REAL"
                )
            if "source_currency" not in existing_columns:
                conn.execute(
                    "ALTER TABLE price_quotes ADD COLUMN source_currency TEXT"
                )
            if "exchange_rate" not in existing_columns:
                conn.execute(
                    "ALTER TABLE price_quotes ADD COLUMN exchange_rate REAL"
                )
            if "flight_number" not in existing_columns:
                conn.execute(
                    "ALTER TABLE price_quotes ADD COLUMN flight_number TEXT"
                )
            if "depart_time" not in existing_columns:
                conn.execute(
                    "ALTER TABLE price_quotes ADD COLUMN depart_time TEXT"
                )
            if "arrive_time" not in existing_columns:
                conn.execute(
                    "ALTER TABLE price_quotes ADD COLUMN arrive_time TEXT"
                )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_key TEXT NOT NULL,
                    fired_at TEXT NOT NULL
                )
                """
            )

    def save_quote(self, quote: PriceQuote) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO price_quotes (
                    origin,
                    destination,
                    depart_date,
                    return_date,
                    total_price,
                    currency,
                    provider,
                    observed_at,
                    source_price,
                    source_currency,
                    exchange_rate,
                    flight_number,
                    depart_time,
                    arrive_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote.route.origin,
                    quote.route.destination,
                    quote.depart_date.isoformat(),
                    quote.return_date.isoformat(),
                    quote.total_price,
                    quote.currency,
                    quote.provider,
                    quote.observed_at.isoformat(),
                    quote.source_price,
                    quote.source_currency,
                    quote.exchange_rate,
                    quote.flight_number,
                    quote.depart_time,
                    quote.arrive_time,
                ),
            )

    def get_historical_low(
        self,
        route: Route,
        depart_date: str,
        return_date: str,
    ) -> float | None:
        with self._connect() as conn:
            result = conn.execute(
                """
                SELECT MIN(total_price)
                FROM price_quotes
                WHERE origin = ?
                  AND destination = ?
                  AND depart_date = ?
                  AND return_date = ?
                """,
                (route.origin, route.destination, depart_date, return_date),
            ).fetchone()
        if result is None or result[0] is None:
            return None
        return float(result[0])

    def get_price_stats(
        self,
        route: Route,
        depart_date: str,
        return_date: str,
        currency: str,
        provider: str | None = None,
        source_currency: str | None = None,
    ) -> dict[str, float | int | None]:
        conditions = [
            "origin = ?",
            "destination = ?",
            "depart_date = ?",
            "return_date = ?",
            "currency = ?",
        ]
        params: list[str] = [
            route.origin,
            route.destination,
            depart_date,
            return_date,
            currency,
        ]
        if provider:
            conditions.append("provider = ?")
            params.append(provider)
        if source_currency:
            conditions.append("source_currency = ?")
            params.append(source_currency)

        with self._connect() as conn:
            result = conn.execute(
                f"""
                SELECT COUNT(*), MIN(total_price), MAX(total_price), AVG(total_price)
                FROM price_quotes
                WHERE {' AND '.join(conditions)}
                """,
                tuple(params),
            ).fetchone()

        count = int(result[0]) if result and result[0] is not None else 0
        min_price = float(result[1]) if result and result[1] is not None else None
        max_price = float(result[2]) if result and result[2] is not None else None
        avg_price = float(result[3]) if result and result[3] is not None else None
        return {
            "count": count,
            "min": min_price,
            "max": max_price,
            "avg": avg_price,
        }

    def should_fire_alert(
        self,
        alert_key: str,
        cooldown_minutes: int,
    ) -> bool:
        deadline = datetime.now() - timedelta(minutes=cooldown_minutes)
        with self._connect() as conn:
            result = conn.execute(
                """
                SELECT fired_at
                FROM alert_events
                WHERE alert_key = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (alert_key,),
            ).fetchone()

        if result is None:
            return True
        last_fired = datetime.fromisoformat(result[0])
        return last_fired <= deadline

    def record_alert(self, alert_key: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alert_events (alert_key, fired_at)
                VALUES (?, ?)
                """,
                (alert_key, datetime.now().isoformat()),
            )
