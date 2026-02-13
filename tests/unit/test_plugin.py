from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from flakyguard.core.models import FlakyGuardConfig, FlakyTest, QuarantineMode, TestOutcome
from flakyguard.plugin import FlakyGuardPlugin, pytest_addoption, pytest_configure


def test_pytest_addoption_registers_options():
    parser = Mock()
    group = Mock()
    parser.getgroup.return_value = group

    pytest_addoption(parser)

    parser.getgroup.assert_called_once_with("flakyguard")
    options = [call.args[0] for call in group.addoption.call_args_list]
    assert "--flakyguard" in options
    assert "--flakyguard-mode" in options
    assert "--flakyguard-threshold" in options
    assert "--flakyguard-window" in options
    assert "--flakyguard-db" in options
    assert "--flakyguard-retry-count" in options


@patch("flakyguard.plugin.FlakyGuardPlugin")
@patch("flakyguard.plugin.SQLiteStorage")
def test_pytest_configure_enabled_registers_plugin(mock_storage_cls, mock_plugin_cls):
    config = Mock()
    config.pluginmanager = Mock()
    options = {
        "--flakyguard": True,
        "--flakyguard-mode": "retry",
        "--flakyguard-threshold": 0.2,
        "--flakyguard-window": 25,
        "--flakyguard-db": "tmp/flakyguard.db",
        "--flakyguard-retry-count": 4,
    }
    config.getoption.side_effect = options.__getitem__

    storage = Mock()
    mock_storage_cls.return_value = storage
    plugin = Mock()
    mock_plugin_cls.return_value = plugin

    pytest_configure(config)

    config.addinivalue_line.assert_any_call(
        "markers", "flakyguard: Mark test as tracked by FlakyGuard"
    )
    config.addinivalue_line.assert_any_call(
        "markers", "flaky: Mark test for retry by FlakyGuard"
    )
    flakyguard_config = mock_storage_cls.call_args.args[0]
    assert isinstance(flakyguard_config, FlakyGuardConfig)
    assert flakyguard_config.quarantine_mode == QuarantineMode.RETRY
    assert flakyguard_config.threshold == 0.2
    assert flakyguard_config.window_size == 25
    assert flakyguard_config.retry_count == 4
    assert flakyguard_config.db_path == Path("tmp/flakyguard.db")
    mock_plugin_cls.assert_called_once_with(storage, flakyguard_config)
    config.pluginmanager.register.assert_called_once_with(plugin, "flakyguard-runtime")


@patch("flakyguard.plugin.SQLiteStorage")
def test_pytest_configure_disabled_does_nothing(mock_storage_cls):
    config = Mock()
    config.pluginmanager = Mock()
    config.getoption.return_value = False

    pytest_configure(config)

    config.addinivalue_line.assert_not_called()
    config.pluginmanager.register.assert_not_called()
    mock_storage_cls.assert_not_called()


@patch("flakyguard.plugin.get_strategy")
@patch("flakyguard.plugin.detect_flaky_tests")
def test_collection_modifyitems_detects_and_applies_strategy(mock_detect, mock_get_strategy):
    config = FlakyGuardConfig(window_size=10, threshold=0.05, retry_count=2)
    storage = Mock()
    histories = [Mock()]
    storage.get_all_histories.return_value = histories

    flaky = FlakyTest(
        test_id="tests/test_sample.py::test_flaky",
        flakiness_rate=0.3,
        total_runs=10,
        failures=3,
        last_seen=datetime.now(timezone.utc),
        quarantine_mode=QuarantineMode.WARN,
    )
    mock_detect.return_value = [flaky]
    strategy = Mock()
    mock_get_strategy.return_value = strategy

    flaky_item = Mock()
    flaky_item.nodeid = flaky.test_id
    stable_item = Mock()
    stable_item.nodeid = "tests/test_sample.py::test_stable"

    plugin = FlakyGuardPlugin(storage, config)
    plugin.pytest_collection_modifyitems([flaky_item, stable_item])

    storage.get_all_histories.assert_called_once_with(config.window_size)
    mock_detect.assert_called_once_with(histories, config)
    mock_get_strategy.assert_called_once_with(config.quarantine_mode, config.retry_count)
    strategy.apply.assert_called_once_with(flaky_item, flaky)
    assert plugin.flaky_tests_map[flaky.test_id] == flaky


def test_pytest_runtest_makereport_saves_results():
    config = FlakyGuardConfig()
    storage = Mock()
    plugin = FlakyGuardPlugin(storage, config)

    item = Mock()
    item.nodeid = "tests/test_runtime.py::test_example"
    report = Mock()
    report.when = "call"
    report.outcome = "failed"
    report.duration = 1.23
    outcome = Mock()
    outcome.get_result.return_value = report

    generator = plugin.pytest_runtest_makereport(item, call=Mock())
    next(generator)
    with pytest.raises(StopIteration):
        generator.send(outcome)

    storage.save_result.assert_called_once()
    saved_result = storage.save_result.call_args.args[0]
    assert saved_result.test_id == item.nodeid
    assert saved_result.outcome == TestOutcome.FAILED
    assert saved_result.duration == 1.23


@patch("flakyguard.plugin.detect_flaky_tests")
def test_pytest_terminal_summary_reports_flaky_tests(mock_detect):
    config = FlakyGuardConfig(window_size=10, threshold=0.05)
    storage = Mock()
    storage.get_all_histories.return_value = [Mock()]
    plugin = FlakyGuardPlugin(storage, config)

    flaky = FlakyTest(
        test_id="tests/test_terminal.py::test_flaky",
        flakiness_rate=0.25,
        total_runs=20,
        failures=5,
        last_seen=datetime.now(timezone.utc),
        quarantine_mode=QuarantineMode.WARN,
    )
    mock_detect.return_value = [flaky]

    terminalreporter = MagicMock()
    plugin.pytest_terminal_summary(terminalreporter)

    storage.get_all_histories.assert_called_once_with(config.window_size)
    mock_detect.assert_called_once_with(storage.get_all_histories.return_value, config)
    terminalreporter.section.assert_called_once_with("FlakyGuard Summary")
    lines = [call.args[0] for call in terminalreporter.write_line.call_args_list]
    assert any("Detected 1 flaky test(s)" in line for line in lines)
    assert any(flaky.test_id in line for line in lines)
