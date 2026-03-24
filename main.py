import argparse
from pathlib import Path
import sys

from flight_monitor.config import (
    create_default_config,
    load_config,
    save_config,
)
from flight_monitor.monitor import FlightMonitor
from flight_monitor.notifier import ConsoleNotifier, EmailNotifier
from flight_monitor.providers.amadeus_provider import AmadeusPriceProvider
from flight_monitor.providers.kiwi_provider import KiwiPriceProvider
from flight_monitor.providers.mock_provider import MockPriceProvider
from flight_monitor.providers.trip_scrape_provider import (
    TripScrapePriceProvider,
)
from flight_monitor.storage import PriceStorage


def build_monitor(config_path: Path) -> FlightMonitor:
    config = load_config(config_path)

    provider_name = config.provider.lower().strip()
    if provider_name == "mock":
        provider = MockPriceProvider()
    elif provider_name == "kiwi":
        if not config.kiwi_api_key:
            raise ValueError("provider=kiwi 时必须配置 kiwi_api_key")
        provider = KiwiPriceProvider(api_key=config.kiwi_api_key)
    elif provider_name == "amadeus":
        client_id = config.amadeus_client_id
        client_secret = config.amadeus_client_secret
        required_values = {
            "amadeus_client_id": client_id,
            "amadeus_client_secret": client_secret,
        }
        missing_keys = [
            key for key, value in required_values.items() if not value
        ]
        if missing_keys:
            raise ValueError(
                "provider=amadeus 时缺少配置: "
                + ", ".join(sorted(missing_keys))
            )
        provider = AmadeusPriceProvider(
            client_id=client_id or "",
            client_secret=client_secret or "",
            base_url=config.amadeus_base_url,
        )
    elif provider_name == "trip_scrape":
        provider = TripScrapePriceProvider(
            timeout_seconds=config.trip_scrape_timeout_seconds,
        )
    else:
        raise ValueError(f"不支持的 provider: {config.provider}")

    notifier_name = config.notifier.lower().strip()
    if notifier_name == "console":
        notifier = ConsoleNotifier()
    elif notifier_name == "email":
        smtp_host = config.smtp_host
        smtp_username = config.smtp_username
        smtp_password = config.smtp_password
        email_from = config.email_from
        required_values = {
            "smtp_host": smtp_host,
            "smtp_username": smtp_username,
            "smtp_password": smtp_password,
            "email_from": email_from,
        }
        missing_keys = [
            key for key, value in required_values.items() if not value
        ]
        if not config.email_to:
            missing_keys.append("email_to")
        if missing_keys:
            raise ValueError(
                "notifier=email 时缺少配置: "
                + ", ".join(sorted(missing_keys))
            )

        notifier = EmailNotifier(
            smtp_host=smtp_host or "",
            smtp_port=config.smtp_port,
            smtp_username=smtp_username or "",
            smtp_password=smtp_password or "",
            email_from=email_from or "",
            email_to=config.email_to,
            smtp_use_tls=config.smtp_use_tls,
        )
    else:
        raise ValueError(f"不支持的 notifier: {config.notifier}")

    storage = PriceStorage(Path(config.db_path))
    return FlightMonitor(
        config=config,
        provider=provider,
        storage=storage,
        notifier=notifier,
    )


def cmd_init_config(args: argparse.Namespace) -> None:
    output = Path(args.output)
    if output.exists() and not args.force:
        raise FileExistsError(
            f"配置文件已存在: {output}. 如需覆盖请添加 --force"
        )
    config = create_default_config()
    save_config(config, output)
    print(f"已生成配置文件: {output}")


def cmd_run_once(args: argparse.Namespace) -> None:
    monitor = build_monitor(Path(args.config))
    monitor.run_once(quick=args.quick)


def cmd_run_loop(args: argparse.Namespace) -> None:
    monitor = build_monitor(Path(args.config))
    monitor.run_loop()


def cmd_run_thailand_cheapest(args: argparse.Namespace) -> None:
    monitor = build_monitor(Path(args.config))
    monitor.run_thailand_cheapest()


def cmd_run_best_deals_summary(args: argparse.Namespace) -> None:
    monitor = build_monitor(Path(args.config))
    monitor.run_best_deals_summary()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="机票价格监控")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-config", help="生成默认配置")
    init_parser.add_argument(
        "--output", default="config.yaml", help="输出配置路径"
    )
    init_parser.add_argument(
        "--force", action="store_true", help="覆盖已有配置"
    )
    init_parser.set_defaults(func=cmd_init_config)

    run_once_parser = subparsers.add_parser("run-once", help="执行一次监控")
    run_once_parser.add_argument(
        "--config", default="config.yaml", help="配置文件路径"
    )
    run_once_parser.add_argument(
        "--quick",
        action="store_true",
        help="快速模式：每个出发地仅抓取一个日期组合",
    )
    run_once_parser.set_defaults(func=cmd_run_once)

    run_loop_parser = subparsers.add_parser("run", help="持续运行监控")
    run_loop_parser.add_argument(
        "--config", default="config.yaml", help="配置文件路径"
    )
    run_loop_parser.set_defaults(func=cmd_run_loop)

    thailand_cheapest_parser = subparsers.add_parser(
        "run-thailand-cheapest",
        help="按当前去返日期检索三地到泰国的最低价",
    )
    thailand_cheapest_parser.add_argument(
        "--config", default="config.yaml", help="配置文件路径"
    )
    thailand_cheapest_parser.set_defaults(func=cmd_run_thailand_cheapest)

    deals_summary_parser = subparsers.add_parser(
        "run-best-deals-summary",
        help="仅输出PQC与泰国两类目的地的最终最低价",
    )
    deals_summary_parser.add_argument(
        "--config", default="config.yaml", help="配置文件路径"
    )
    deals_summary_parser.set_defaults(func=cmd_run_best_deals_summary)

    return parser


def main() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(line_buffering=True)

    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
