from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from flakyguard.core.models import FlakyTest, QuarantineMode
from flakyguard.core.quarantine import (
    RetryStrategy,
    SkipStrategy,
    WarnStrategy,
    get_strategy,
)


@pytest.fixture
def flaky_test() -> FlakyTest:
    return FlakyTest(
        test_id="test_example",
        flakiness_rate=0.25,
        total_runs=100,
        failures=25,
        last_seen=datetime.now(timezone.utc),
        quarantine_mode=QuarantineMode.WARN,
    )


@pytest.fixture
def mock_item():
    item = Mock()
    item.add_marker = Mock()
    return item


def test_warn_strategy_adds_xfail_marker(mock_item, flaky_test):
    strategy = WarnStrategy()
    strategy.apply(mock_item, flaky_test)

    mock_item.add_marker.assert_called_once()
    marker = mock_item.add_marker.call_args[0][0]
    assert marker.name == "xfail"
    assert marker.kwargs["strict"] is False
    assert "flaky" in marker.kwargs["reason"].lower()
    assert "25.0%" in marker.kwargs["reason"]


def test_skip_strategy_adds_skip_marker(mock_item, flaky_test):
    strategy = SkipStrategy()
    strategy.apply(mock_item, flaky_test)

    mock_item.add_marker.assert_called_once()
    marker = mock_item.add_marker.call_args[0][0]
    assert marker.name == "skip"
    assert "quarantine" in marker.kwargs["reason"].lower()
    assert "25.0%" in marker.kwargs["reason"]


def test_retry_strategy_adds_flaky_marker(mock_item, flaky_test):
    strategy = RetryStrategy(retry_count=5)
    strategy.apply(mock_item, flaky_test)

    mock_item.add_marker.assert_called_once()
    marker = mock_item.add_marker.call_args[0][0]
    assert marker.name == "flaky"
    assert marker.kwargs["reruns"] == 5
    assert "flaky" in marker.kwargs["reason"].lower()


def test_retry_strategy_default_count(mock_item, flaky_test):
    strategy = RetryStrategy()
    strategy.apply(mock_item, flaky_test)

    marker = mock_item.add_marker.call_args[0][0]
    assert marker.kwargs["reruns"] == 3


def test_get_strategy_warn():
    strategy = get_strategy(QuarantineMode.WARN)
    assert isinstance(strategy, WarnStrategy)


def test_get_strategy_skip():
    strategy = get_strategy(QuarantineMode.SKIP)
    assert isinstance(strategy, SkipStrategy)


def test_get_strategy_retry():
    strategy = get_strategy(QuarantineMode.RETRY, retry_count=5)
    assert isinstance(strategy, RetryStrategy)
    assert strategy.retry_count == 5


def test_get_strategy_invalid_mode():
    with pytest.raises(ValueError, match="Unknown quarantine mode"):
        get_strategy("invalid")  # pyright: ignore[reportArgumentType]
