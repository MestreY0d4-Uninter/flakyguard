from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

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


@pytest.fixture
def temp_db():
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest.fixture
def storage(temp_db):
    config = FlakyGuardConfig(
        window_size=50, threshold=0.05, quarantine_mode=QuarantineMode.WARN, db_path=temp_db
    )
    return SQLiteStorage(config)


@pytest.fixture
def env_info() -> EnvironmentInfo:
    return EnvironmentInfo(
        python_version="3.10.0",
        platform="linux",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def make_result(env_info):
    def _make(test_id: str, outcome: TestOutcome) -> TestResult:
        return TestResult(
            test_id=test_id,
            outcome=outcome,
            duration=1.0,
            timestamp=datetime.now(timezone.utc),
            environment_info=env_info,
        )

    return _make


def test_storage_initialization(temp_db):
    config = FlakyGuardConfig(db_path=temp_db)
    storage = SQLiteStorage(config)

    assert temp_db.exists()
    storage.close()


def test_save_and_retrieve_result(storage, make_result):
    result = make_result("test_example", TestOutcome.PASSED)
    storage.save_result(result)

    history = storage.get_history("test_example", 10)
    assert history is not None
    assert len(history.results) == 1
    assert history.results[0].test_id == "test_example"
    assert history.results[0].outcome == TestOutcome.PASSED


def test_save_multiple_results(storage, make_result):
    for i in range(5):
        outcome = TestOutcome.PASSED if i % 2 == 0 else TestOutcome.FAILED
        storage.save_result(make_result("test_example", outcome))

    history = storage.get_history("test_example", 10)
    assert history is not None
    assert len(history.results) == 5


def test_get_history_respects_window_size(storage, make_result):
    for _ in range(10):
        storage.save_result(make_result("test_example", TestOutcome.PASSED))

    history = storage.get_history("test_example", 5)
    assert history is not None
    assert len(history.results) == 5


def test_get_history_returns_none_for_unknown_test(storage):
    history = storage.get_history("nonexistent_test", 10)
    assert history is None


def test_get_all_histories(storage, make_result):
    storage.save_result(make_result("test_one", TestOutcome.PASSED))
    storage.save_result(make_result("test_two", TestOutcome.FAILED))
    storage.save_result(make_result("test_one", TestOutcome.PASSED))

    histories = storage.get_all_histories(10)
    assert len(histories) == 2

    test_ids = {h.test_id for h in histories}
    assert test_ids == {"test_one", "test_two"}


def test_detect_flaky_tests_detects_instability(storage, make_result):
    for i in range(10):
        outcome = TestOutcome.PASSED if i % 2 == 0 else TestOutcome.FAILED
        storage.save_result(make_result("test_flaky", outcome))

    for _ in range(10):
        storage.save_result(make_result("test_stable", TestOutcome.PASSED))

    config = FlakyGuardConfig(window_size=50, threshold=0.05)
    histories = storage.get_all_histories(config.window_size)
    flaky_tests = detect_flaky_tests(histories, config)
    assert len(flaky_tests) == 1
    assert flaky_tests[0].test_id == "test_flaky"


def test_clear_removes_all_results(storage, make_result):
    storage.save_result(make_result("test_one", TestOutcome.PASSED))
    storage.save_result(make_result("test_two", TestOutcome.FAILED))

    storage.clear()

    histories = storage.get_all_histories(10)
    assert len(histories) == 0


def test_result_ordering_preserved(storage, make_result, env_info):
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    for i in range(5):
        result = TestResult(
            test_id="test_example",
            outcome=TestOutcome.PASSED,
            duration=1.0,
            timestamp=base_time.replace(second=i),
            environment_info=env_info,
        )
        storage.save_result(result)

    history = storage.get_history("test_example", 10)
    assert history is not None

    for i in range(len(history.results) - 1):
        assert history.results[i].timestamp < history.results[i + 1].timestamp
