import platform
import sys
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from flakyguard.adapters.storage import SQLiteStorage
from flakyguard.core.detector import detect_flaky_tests
from flakyguard.core.models import (
    EnvironmentInfo,
    FlakyGuardConfig,
    QuarantineMode,
    TestOutcome,
    TestResult,
)
from flakyguard.core.quarantine import get_strategy
from flakyguard.ports.protocols import StoragePort


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("flakyguard")

    group.addoption(
        "--flakyguard",
        action="store_true",
        default=False,
        help="Enable FlakyGuard flaky test detection and tracking",
    )

    group.addoption(
        "--flakyguard-mode",
        choices=["warn", "skip", "retry"],
        default="warn",
        help="Quarantine mode for flaky tests (default: warn)",
    )

    group.addoption(
        "--flakyguard-threshold",
        type=float,
        default=0.05,
        help="Flakiness threshold (default: 0.05)",
    )

    group.addoption(
        "--flakyguard-window",
        type=int,
        default=50,
        help="Window size for history analysis (default: 50)",
    )

    group.addoption(
        "--flakyguard-db",
        type=str,
        default=".flakyguard/history.db",
        help="Path to database file (default: .flakyguard/history.db)",
    )

    group.addoption(
        "--flakyguard-retry-count",
        type=int,
        default=3,
        help="Number of retries in retry mode (default: 3)",
    )


def pytest_configure(config: Any) -> None:
    if not config.getoption("--flakyguard"):
        return

    config.addinivalue_line("markers", "flakyguard: Mark test as tracked by FlakyGuard")
    config.addinivalue_line(
        "markers", "flaky: Mark test for retry by FlakyGuard"
    )

    quarantine_mode_str = config.getoption("--flakyguard-mode")
    quarantine_mode = QuarantineMode(quarantine_mode_str)

    flakyguard_config = FlakyGuardConfig(
        window_size=config.getoption("--flakyguard-window"),
        threshold=config.getoption("--flakyguard-threshold"),
        quarantine_mode=quarantine_mode,
        db_path=Path(config.getoption("--flakyguard-db")),
        retry_count=config.getoption("--flakyguard-retry-count"),
    )

    storage = SQLiteStorage(flakyguard_config)

    config.pluginmanager.register(
        FlakyGuardPlugin(storage, flakyguard_config), "flakyguard-runtime"
    )


class FlakyGuardPlugin:
    def __init__(self, storage: StoragePort, config: FlakyGuardConfig) -> None:
        self.storage = storage
        self.config = config
        self.flaky_tests_map: dict[str, Any] = {}

    def pytest_collection_modifyitems(self, items: list[Any]) -> None:
        histories = self.storage.get_all_histories(self.config.window_size)
        flaky_tests = detect_flaky_tests(histories, self.config)

        for flaky in flaky_tests:
            self.flaky_tests_map[flaky.test_id] = flaky

        if not flaky_tests:
            return

        strategy = get_strategy(self.config.quarantine_mode, self.config.retry_count)

        for item in items:
            test_id = item.nodeid
            if test_id in self.flaky_tests_map:
                flaky = self.flaky_tests_map[test_id]
                strategy.apply(item, flaky)

    @pytest.hookimpl(tryfirst=True, hookwrapper=True)
    def pytest_runtest_makereport(
        self, item: Any, call: Any
    ) -> Generator[None, Any, None]:
        outcome = yield
        report = outcome.get_result()

        if report.when != "call":
            return

        test_id = item.nodeid

        outcome_map = {
            "passed": TestOutcome.PASSED,
            "failed": TestOutcome.FAILED,
            "skipped": TestOutcome.SKIPPED,
        }

        test_outcome = outcome_map.get(report.outcome, TestOutcome.ERROR)

        env_info = EnvironmentInfo(
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            platform=platform.system().lower(),
            timestamp=datetime.now(timezone.utc),
        )

        result = TestResult(
            test_id=test_id,
            outcome=test_outcome,
            duration=getattr(report, "duration", 0.0),
            timestamp=datetime.now(timezone.utc),
            environment_info=env_info,
        )

        self.storage.save_result(result)

    def pytest_terminal_summary(self, terminalreporter: Any) -> None:
        histories = self.storage.get_all_histories(self.config.window_size)
        flaky_tests = detect_flaky_tests(histories, self.config)

        if not flaky_tests:
            return

        terminalreporter.section("FlakyGuard Summary")
        terminalreporter.write_line(
            f"Detected {len(flaky_tests)} flaky test(s) "
            f"(threshold: {self.config.threshold:.1%}, window: {self.config.window_size})"
        )
        terminalreporter.write_line("")

        for flaky in flaky_tests[:10]:
            status_color = "red" if flaky.flakiness_rate > 0.2 else "yellow"
            terminalreporter.write_line(
                f"  - {flaky.test_id}: "
                f"{flaky.flakiness_rate:.1%} flaky "
                f"({flaky.failures}/{flaky.total_runs} failures)",
                **{status_color: True},
            )

        if len(flaky_tests) > 10:
            terminalreporter.write_line(f"  ... and {len(flaky_tests) - 10} more")

        terminalreporter.write_line("")
        terminalreporter.write_line(
            "Run 'flakyguard report' for detailed information."
        )
