from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest

from flakyguard.core.detector import detect_flaky_tests
from flakyguard.core.models import (
    EnvironmentInfo,
    FlakyGuardConfig,
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
def make_history(
    env_info: EnvironmentInfo,
) -> Callable[[str, list[TestOutcome]], TestHistory]:
    def _make(test_id: str, outcomes: list[TestOutcome]) -> TestHistory:
        results = []
        base_time = datetime.now(timezone.utc)

        for i, outcome in enumerate(outcomes):
            result = TestResult(
                test_id=test_id,
                outcome=outcome,
                duration=1.0,
                timestamp=base_time + timedelta(seconds=i),
                environment_info=env_info,
            )
            results.append(result)

        return TestHistory(test_id=test_id, results=tuple(results))

    return _make


def test_detect_no_flaky_tests_all_pass(make_history):
    config = FlakyGuardConfig(window_size=10, threshold=0.05)
    history = make_history("test_stable", [TestOutcome.PASSED] * 10)

    flaky_tests = detect_flaky_tests([history], config)

    assert len(flaky_tests) == 0


def test_detect_empty_histories():
    config = FlakyGuardConfig(window_size=10, threshold=0.05)

    flaky_tests = detect_flaky_tests([], config)

    assert flaky_tests == []


def test_detect_no_flaky_tests_all_fail(make_history):
    config = FlakyGuardConfig(window_size=10, threshold=0.05)
    history = make_history("test_broken", [TestOutcome.FAILED] * 10)

    flaky_tests = detect_flaky_tests([history], config)

    assert len(flaky_tests) == 0


def test_detect_flaky_test(make_history):
    config = FlakyGuardConfig(window_size=10, threshold=0.05)
    outcomes = [
        TestOutcome.PASSED,
        TestOutcome.FAILED,
        TestOutcome.PASSED,
        TestOutcome.PASSED,
        TestOutcome.PASSED,
    ]
    history = make_history("test_flaky", outcomes)

    flaky_tests = detect_flaky_tests([history], config)

    assert len(flaky_tests) == 1
    assert flaky_tests[0].test_id == "test_flaky"
    assert flaky_tests[0].flakiness_rate == 0.2
    assert flaky_tests[0].total_runs == 5
    assert flaky_tests[0].failures == 1


def test_detect_flaky_test_with_error(make_history):
    config = FlakyGuardConfig(window_size=10, threshold=0.05)
    outcomes = [
        TestOutcome.PASSED,
        TestOutcome.ERROR,
        TestOutcome.PASSED,
        TestOutcome.PASSED,
        TestOutcome.PASSED,
    ]
    history = make_history("test_flaky", outcomes)

    flaky_tests = detect_flaky_tests([history], config)

    assert len(flaky_tests) == 1
    assert flaky_tests[0].failures == 1


def test_detect_respects_threshold(make_history):
    config_low = FlakyGuardConfig(window_size=100, threshold=0.04)
    config_high = FlakyGuardConfig(window_size=100, threshold=0.10)

    outcomes = [TestOutcome.PASSED] * 95 + [TestOutcome.FAILED] * 5
    history = make_history("test_borderline", outcomes)

    flaky_low = detect_flaky_tests([history], config_low)
    flaky_high = detect_flaky_tests([history], config_high)

    assert len(flaky_low) == 1
    assert len(flaky_high) == 0


def test_detect_sorts_by_flakiness_rate(make_history):
    config = FlakyGuardConfig(window_size=10, threshold=0.05)

    history1 = make_history(
        "test_very_flaky",
        [TestOutcome.PASSED, TestOutcome.FAILED] * 5,
    )
    history2 = make_history(
        "test_less_flaky",
        [TestOutcome.PASSED] * 9 + [TestOutcome.FAILED],
    )

    flaky_tests = detect_flaky_tests([history1, history2], config)

    assert len(flaky_tests) == 2
    assert flaky_tests[0].test_id == "test_very_flaky"
    assert flaky_tests[1].test_id == "test_less_flaky"
    assert flaky_tests[0].flakiness_rate > flaky_tests[1].flakiness_rate


def test_detect_respects_window_size(make_history):
    config = FlakyGuardConfig(window_size=5, threshold=0.05)

    outcomes = (
        [TestOutcome.PASSED] * 10 + [TestOutcome.FAILED] * 5 + [TestOutcome.PASSED] * 5
    )
    history = make_history("test_recent_stable", outcomes)

    flaky_tests = detect_flaky_tests([history], config)

    assert len(flaky_tests) == 0


def test_detect_applies_quarantine_mode(make_history):
    config = FlakyGuardConfig(
        window_size=10, threshold=0.05, quarantine_mode=QuarantineMode.SKIP
    )
    outcomes = [TestOutcome.PASSED, TestOutcome.FAILED] * 3
    history = make_history("test_flaky", outcomes)

    flaky_tests = detect_flaky_tests([history], config)

    assert len(flaky_tests) == 1
    assert flaky_tests[0].quarantine_mode == QuarantineMode.SKIP
