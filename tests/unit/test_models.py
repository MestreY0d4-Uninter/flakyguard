from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from flakyguard.core.models import (
    EnvironmentInfo,
    FlakyGuardConfig,
    FlakyTest,
    QuarantineMode,
    TestHistory,
    TestOutcome,
    TestResult,
)


@pytest.fixture
def env_info() -> EnvironmentInfo:
    return EnvironmentInfo(
        python_version="3.10.0",
        platform="linux",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def make_result(
    env_info: EnvironmentInfo,
) -> Callable[[str, TestOutcome, float], TestResult]:
    def _make(test_id: str, outcome: TestOutcome, duration: float = 1.0) -> TestResult:
        return TestResult(
            test_id=test_id,
            outcome=outcome,
            duration=duration,
            timestamp=datetime.now(timezone.utc),
            environment_info=env_info,
        )

    return _make


def test_test_result_creation(make_result):
    result = make_result("test_example", TestOutcome.PASSED)
    assert result.test_id == "test_example"
    assert result.outcome == TestOutcome.PASSED
    assert result.duration >= 0


def test_test_result_immutable(make_result):
    result = make_result("test_example", TestOutcome.PASSED)
    with pytest.raises(ValidationError):
        result.outcome = TestOutcome.FAILED


def test_test_history_flakiness_rate_all_pass(make_result):
    results = tuple(make_result(f"test_{i}", TestOutcome.PASSED) for i in range(10))
    history = TestHistory(test_id="test_example", results=results)
    assert history.flakiness_rate(window_size=10) == 0.0


def test_test_history_flakiness_rate_all_fail(make_result):
    results = tuple(make_result(f"test_{i}", TestOutcome.FAILED) for i in range(10))
    history = TestHistory(test_id="test_example", results=results)
    assert history.flakiness_rate(window_size=10) == 1.0


def test_test_history_flakiness_rate_half_fail(make_result):
    results = tuple(
        make_result(
            f"test_{i}",
            TestOutcome.FAILED if i % 2 == 0 else TestOutcome.PASSED,
        )
        for i in range(10)
    )
    history = TestHistory(test_id="test_example", results=results)
    assert history.flakiness_rate(window_size=10) == 0.5


def test_test_history_flakiness_rate_window(make_result):
    results = (
        *tuple(make_result(f"test_{i}", TestOutcome.PASSED) for i in range(5)),
        *tuple(make_result(f"test_{i}", TestOutcome.FAILED) for i in range(5, 10)),
    )
    history = TestHistory(test_id="test_example", results=results)
    assert history.flakiness_rate(window_size=5) == 1.0
    assert history.flakiness_rate(window_size=10) == 0.5


def test_test_history_is_flaky_requires_both_outcomes(make_result):
    all_pass = tuple(make_result(f"test_{i}", TestOutcome.PASSED) for i in range(10))
    history = TestHistory(test_id="test_example", results=all_pass)
    assert not history.is_flaky(window_size=10, threshold=0.05)

    all_fail = tuple(make_result(f"test_{i}", TestOutcome.FAILED) for i in range(10))
    history = TestHistory(test_id="test_example", results=all_fail)
    assert not history.is_flaky(window_size=10, threshold=0.05)


def test_test_history_is_flaky_detects_instability(make_result):
    results = (
        make_result("test_0", TestOutcome.PASSED),
        make_result("test_1", TestOutcome.FAILED),
        make_result("test_2", TestOutcome.PASSED),
        make_result("test_3", TestOutcome.PASSED),
        make_result("test_4", TestOutcome.PASSED),
    )
    history = TestHistory(test_id="test_example", results=results)
    assert history.is_flaky(window_size=10, threshold=0.05)


def test_test_history_is_flaky_respects_threshold(make_result):
    results = (
        *tuple(make_result(f"test_{i}", TestOutcome.PASSED) for i in range(95)),
        *tuple(make_result(f"test_{i}", TestOutcome.FAILED) for i in range(95, 100)),
    )
    history = TestHistory(test_id="test_example", results=results)
    assert not history.is_flaky(window_size=100, threshold=0.10)
    assert history.is_flaky(window_size=100, threshold=0.04)


def test_test_history_is_flaky_requires_min_runs(make_result):
    single_result = (make_result("test_0", TestOutcome.PASSED),)
    history = TestHistory(test_id="test_example", results=single_result)
    assert not history.is_flaky(window_size=10, threshold=0.05)


def test_flaky_test_creation():
    flaky = FlakyTest(
        test_id="test_example",
        flakiness_rate=0.15,
        total_runs=100,
        failures=15,
        last_seen=datetime.now(timezone.utc),
        quarantine_mode=QuarantineMode.WARN,
    )
    assert flaky.test_id == "test_example"
    assert flaky.flakiness_rate == 0.15
    assert flaky.quarantine_mode == QuarantineMode.WARN


def test_flaky_guard_config_defaults():
    config = FlakyGuardConfig()
    assert config.window_size == 50
    assert config.threshold == 0.05
    assert config.quarantine_mode == QuarantineMode.WARN
    assert str(config.db_path) == ".flakyguard/history.db"
    assert config.retry_count == 3


def test_flaky_guard_config_custom():
    config = FlakyGuardConfig(
        window_size=100,
        threshold=0.1,
        quarantine_mode=QuarantineMode.SKIP,
        db_path=Path("/custom/path.db"),
        retry_count=5,
    )
    assert config.window_size == 100
    assert config.threshold == 0.1
    assert config.quarantine_mode == QuarantineMode.SKIP
    assert str(config.db_path) == "/custom/path.db"
    assert config.retry_count == 5


def test_flaky_guard_config_validation():
    with pytest.raises(ValueError):
        FlakyGuardConfig(window_size=0)

    with pytest.raises(ValueError):
        FlakyGuardConfig(threshold=-0.1)

    with pytest.raises(ValueError):
        FlakyGuardConfig(threshold=1.5)

    with pytest.raises(ValueError):
        FlakyGuardConfig(retry_count=0)
