from datetime import datetime, timezone
from io import StringIO

import pytest
from rich.console import Console

from flakyguard.core.models import FlakyTest, QuarantineMode
from flakyguard.reporter import RichReporter


@pytest.fixture
def captured_console():
    output = StringIO()
    console = Console(file=output, force_terminal=True)
    return console, output


def test_reporter_empty_list(captured_console):
    console, output = captured_console
    reporter = RichReporter(console=console)

    reporter.report([])

    result = output.getvalue()
    assert "no flaky tests" in result.lower()


def test_reporter_single_flaky_test(captured_console):
    console, output = captured_console
    reporter = RichReporter(console=console)

    flaky = FlakyTest(
        test_id="test_example",
        flakiness_rate=0.25,
        total_runs=100,
        failures=25,
        last_seen=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        quarantine_mode=QuarantineMode.WARN,
    )

    reporter.report([flaky])

    result = output.getvalue()
    assert "test_example" in result
    assert "25.0%" in result or "25%" in result
    assert "100" in result


def test_reporter_multiple_flaky_tests(captured_console):
    console, output = captured_console
    reporter = RichReporter(console=console)

    flaky_tests = [
        FlakyTest(
            test_id="test_very_flaky",
            flakiness_rate=0.5,
            total_runs=100,
            failures=50,
            last_seen=datetime.now(timezone.utc),
            quarantine_mode=QuarantineMode.SKIP,
        ),
        FlakyTest(
            test_id="test_less_flaky",
            flakiness_rate=0.05,
            total_runs=100,
            failures=5,
            last_seen=datetime.now(timezone.utc),
            quarantine_mode=QuarantineMode.WARN,
        ),
    ]

    reporter.report(flaky_tests)

    result = output.getvalue()
    assert "test_very" in result
    assert "test_less" in result
    assert "summary" in result.lower()


def test_reporter_shows_summary(captured_console):
    console, output = captured_console
    reporter = RichReporter(console=console)

    flaky_tests = [
        FlakyTest(
            test_id=f"test_high_{i}",
            flakiness_rate=0.3,
            total_runs=100,
            failures=30,
            last_seen=datetime.now(timezone.utc),
            quarantine_mode=QuarantineMode.WARN,
        )
        for i in range(2)
    ]

    reporter.report(flaky_tests)

    result = output.getvalue()
    assert "most flaky" in result.lower()
    assert "summary" in result.lower()


def test_reporter_handles_no_quarantine_mode(captured_console):
    console, output = captured_console
    reporter = RichReporter(console=console)

    flaky = FlakyTest(
        test_id="test_example",
        flakiness_rate=0.1,
        total_runs=100,
        failures=10,
        last_seen=datetime.now(timezone.utc),
        quarantine_mode=None,
    )

    reporter.report([flaky])

    result = output.getvalue()
    assert "test_example" in result
