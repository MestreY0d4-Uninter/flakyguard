import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import flakyguard.cli as cli_module
from flakyguard.cli import (
    clear_command,
    list_command,
    main,
    report_command,
)
from flakyguard.core.models import FlakyGuardConfig, FlakyTest, QuarantineMode


def test_add_common_args_adds_expected_arguments():
    parser = argparse.ArgumentParser()
    attr_name = "_add_common_args"
    add_common_args = getattr(cli_module, attr_name)
    add_common_args(parser)

    option_strings = {option for action in parser._actions for option in action.option_strings}
    assert {"--db", "--window", "--threshold", "--mode"} <= option_strings

    args = parser.parse_args([])
    assert args.db == ".flakyguard/history.db"
    assert args.window == 50
    assert args.threshold == 0.05
    assert args.mode == "warn"


@patch("flakyguard.cli.RichReporter")
@patch("flakyguard.cli.detect_flaky_tests")
@patch("flakyguard.cli.SQLiteStorage")
def test_report_command_creates_storage_detects_and_reports(
    mock_storage_cls, mock_detect, mock_reporter_cls
):
    storage = Mock()
    histories = [Mock()]
    storage.get_all_histories.return_value = histories
    mock_storage_cls.return_value = storage

    flaky_tests = [Mock()]
    mock_detect.return_value = flaky_tests
    reporter = Mock()
    mock_reporter_cls.return_value = reporter

    report_command("tmp/report.db", 20, 0.2, "skip")

    flakyguard_config = mock_storage_cls.call_args.args[0]
    assert isinstance(flakyguard_config, FlakyGuardConfig)
    assert flakyguard_config.db_path == Path("tmp/report.db")
    assert flakyguard_config.window_size == 20
    assert flakyguard_config.threshold == 0.2
    assert flakyguard_config.quarantine_mode == QuarantineMode.SKIP
    storage.get_all_histories.assert_called_once_with(20)
    mock_detect.assert_called_once_with(histories, flakyguard_config)
    reporter.report.assert_called_once_with(flaky_tests)
    storage.close.assert_called_once()


@patch("flakyguard.cli.Console")
@patch("flakyguard.cli.detect_flaky_tests")
@patch("flakyguard.cli.SQLiteStorage")
def test_list_command_prints_flaky_tests(mock_storage_cls, mock_detect, mock_console_cls):
    storage = Mock()
    storage.get_all_histories.return_value = [Mock()]
    mock_storage_cls.return_value = storage
    console = Mock()
    mock_console_cls.return_value = console
    flaky = FlakyTest(
        test_id="tests/test_cli.py::test_flaky",
        flakiness_rate=0.1,
        total_runs=10,
        failures=1,
        last_seen=datetime.now(timezone.utc),
        quarantine_mode=QuarantineMode.WARN,
    )
    mock_detect.return_value = [flaky]

    list_command("tmp/list.db", 10, 0.05, "warn")

    console.print.assert_any_call("Found 1 flaky test(s):")
    console.print.assert_any_call(f"  - {flaky.test_id} ({flaky.flakiness_rate:.1%})")
    storage.close.assert_called_once()


@patch("flakyguard.cli.Console")
@patch("flakyguard.cli.detect_flaky_tests")
@patch("flakyguard.cli.SQLiteStorage")
def test_list_command_prints_no_flaky_tests_message(
    mock_storage_cls, mock_detect, mock_console_cls
):
    storage = Mock()
    storage.get_all_histories.return_value = [Mock()]
    mock_storage_cls.return_value = storage
    console = Mock()
    mock_console_cls.return_value = console
    mock_detect.return_value = []

    list_command("tmp/list.db", 10, 0.05, "warn")

    console.print.assert_called_once_with("[green]No flaky tests detected.[/green]")
    storage.close.assert_called_once()


@patch("flakyguard.cli.input")
@patch("flakyguard.cli.SQLiteStorage")
@patch("flakyguard.cli.Console")
def test_clear_command_force_true_clears_without_prompt(
    mock_console_cls, mock_storage_cls, mock_input
):
    console = Mock()
    mock_console_cls.return_value = console
    storage = Mock()
    mock_storage_cls.return_value = storage

    clear_command("tmp/clear.db", force=True)

    mock_input.assert_not_called()
    storage.clear.assert_called_once()
    storage.close.assert_called_once()
    console.print.assert_any_call("[green]Test history cleared successfully.[/green]")


@patch("flakyguard.cli.input", return_value="no")
@patch("flakyguard.cli.SQLiteStorage")
@patch("flakyguard.cli.Console")
def test_clear_command_force_false_prompts_user(
    mock_console_cls, mock_storage_cls, mock_input
):
    console = Mock()
    mock_console_cls.return_value = console

    clear_command("tmp/clear.db", force=False)

    mock_input.assert_called_once_with("Are you sure? (yes/no): ")
    console.print.assert_any_call("[yellow]This will delete all test history.[/yellow]")
    console.print.assert_any_call("[red]Aborted.[/red]")
    mock_storage_cls.assert_not_called()


@patch("flakyguard.cli.clear_command")
@patch("flakyguard.cli.list_command")
@patch("flakyguard.cli.report_command")
def test_main_dispatches_report_command(mock_report_command, mock_list_command, mock_clear_command):
    with patch.object(
        sys,
        "argv",
        [
            "flakyguard",
            "report",
            "--db",
            "db.sqlite",
            "--window",
            "7",
            "--threshold",
            "0.2",
            "--mode",
            "retry",
        ],
    ):
        main()

    mock_report_command.assert_called_once_with("db.sqlite", 7, 0.2, "retry")
    mock_list_command.assert_not_called()
    mock_clear_command.assert_not_called()


@patch("flakyguard.cli.clear_command")
@patch("flakyguard.cli.list_command")
@patch("flakyguard.cli.report_command")
def test_main_dispatches_list_command(mock_report_command, mock_list_command, mock_clear_command):
    with patch.object(
        sys,
        "argv",
        [
            "flakyguard",
            "list",
            "--db",
            "db.sqlite",
            "--window",
            "12",
            "--threshold",
            "0.1",
            "--mode",
            "warn",
        ],
    ):
        main()

    mock_list_command.assert_called_once_with("db.sqlite", 12, 0.1, "warn")
    mock_report_command.assert_not_called()
    mock_clear_command.assert_not_called()


@patch("flakyguard.cli.clear_command")
@patch("flakyguard.cli.list_command")
@patch("flakyguard.cli.report_command")
def test_main_dispatches_clear_command(mock_report_command, mock_list_command, mock_clear_command):
    with patch.object(sys, "argv", ["flakyguard", "clear", "--db", "db.sqlite", "--force"]):
        main()

    mock_clear_command.assert_called_once_with("db.sqlite", True)
    mock_report_command.assert_not_called()
    mock_list_command.assert_not_called()
