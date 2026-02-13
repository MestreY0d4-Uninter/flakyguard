import argparse
import sys
from pathlib import Path

from rich.console import Console

from flakyguard.adapters.storage import SQLiteStorage
from flakyguard.core.detector import detect_flaky_tests
from flakyguard.core.models import FlakyGuardConfig, QuarantineMode
from flakyguard.reporter import RichReporter


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=".flakyguard/history.db", help="Database path")
    parser.add_argument(
        "--window", type=int, default=50, help="Window size for analysis"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.05, help="Flakiness threshold"
    )
    parser.add_argument(
        "--mode",
        choices=["warn", "skip", "retry"],
        default="warn",
        help="Quarantine mode",
    )


def report_command(
    db_path: str, window_size: int, threshold: float, quarantine_mode: str
) -> None:
    config = FlakyGuardConfig(
        db_path=Path(db_path),
        window_size=window_size,
        threshold=threshold,
        quarantine_mode=QuarantineMode(quarantine_mode),
    )

    storage = SQLiteStorage(config)
    histories = storage.get_all_histories(config.window_size)
    flaky_tests = detect_flaky_tests(histories, config)

    reporter = RichReporter()
    reporter.report(flaky_tests)

    storage.close()


def list_command(
    db_path: str, window_size: int, threshold: float, quarantine_mode: str
) -> None:
    config = FlakyGuardConfig(
        db_path=Path(db_path),
        window_size=window_size,
        threshold=threshold,
        quarantine_mode=QuarantineMode(quarantine_mode),
    )

    storage = SQLiteStorage(config)
    histories = storage.get_all_histories(config.window_size)
    flaky_tests = detect_flaky_tests(histories, config)

    console = Console()
    if not flaky_tests:
        console.print("[green]No flaky tests detected.[/green]")
    else:
        console.print(f"Found {len(flaky_tests)} flaky test(s):")
        for flaky in flaky_tests:
            console.print(f"  - {flaky.test_id} ({flaky.flakiness_rate:.1%})")

    storage.close()


def clear_command(db_path: str, force: bool) -> None:
    console = Console()
    if not force:
        console.print("[yellow]This will delete all test history.[/yellow]")
        response = input("Are you sure? (yes/no): ").strip().lower()
        if response != "yes":
            console.print("[red]Aborted.[/red]")
            return

    config = FlakyGuardConfig(db_path=Path(db_path))
    storage = SQLiteStorage(config)
    storage.clear()
    storage.close()

    console.print("[green]Test history cleared successfully.[/green]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FlakyGuard - Detect and manage flaky tests"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    report_parser = subparsers.add_parser("report", help="Show detailed flaky tests report")
    _add_common_args(report_parser)

    list_parser = subparsers.add_parser("list", help="List flaky tests")
    _add_common_args(list_parser)

    clear_parser = subparsers.add_parser("clear", help="Clear test history")
    clear_parser.add_argument("--db", default=".flakyguard/history.db", help="Database path")
    clear_parser.add_argument("--force", action="store_true", help="Skip confirmation")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "report":
        report_command(args.db, args.window, args.threshold, args.mode)
    elif args.command == "list":
        list_command(args.db, args.window, args.threshold, args.mode)
    elif args.command == "clear":
        clear_command(args.db, args.force)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
