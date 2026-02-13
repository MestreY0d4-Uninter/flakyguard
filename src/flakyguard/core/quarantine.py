from abc import ABC, abstractmethod
from typing import Any

import pytest

from flakyguard.core.models import FlakyTest, QuarantineMode


class QuarantineStrategy(ABC):
    @abstractmethod
    def apply(self, item: Any, flaky_test: FlakyTest) -> None: ...


class WarnStrategy(QuarantineStrategy):
    def apply(self, item: Any, flaky_test: FlakyTest) -> None:
        marker = pytest.mark.xfail(
            strict=False,
            reason=(
                f"Test is flaky (rate: {flaky_test.flakiness_rate:.1%}, "
                f"failures: {flaky_test.failures}/{flaky_test.total_runs})"
            ),
        )
        item.add_marker(marker)


class SkipStrategy(QuarantineStrategy):
    def apply(self, item: Any, flaky_test: FlakyTest) -> None:
        marker = pytest.mark.skip(
            reason=(
                f"Test in quarantine (flaky rate: {flaky_test.flakiness_rate:.1%}, "
                f"failures: {flaky_test.failures}/{flaky_test.total_runs})"
            ),
        )
        item.add_marker(marker)


class RetryStrategy(QuarantineStrategy):
    def __init__(self, retry_count: int = 3) -> None:
        self.retry_count = retry_count

    def apply(self, item: Any, flaky_test: FlakyTest) -> None:
        marker = pytest.mark.flaky(
            reruns=self.retry_count,
            reason=(
                f"Test is flaky (rate: {flaky_test.flakiness_rate:.1%}, "
                f"retrying up to {self.retry_count} times)"
            ),
        )
        item.add_marker(marker)


def get_strategy(mode: QuarantineMode, retry_count: int = 3) -> QuarantineStrategy:
    strategies: dict[QuarantineMode, QuarantineStrategy] = {
        QuarantineMode.WARN: WarnStrategy(),
        QuarantineMode.SKIP: SkipStrategy(),
        QuarantineMode.RETRY: RetryStrategy(retry_count),
    }

    strategy = strategies.get(mode)
    if strategy is None:
        raise ValueError(f"Unknown quarantine mode: {mode}")

    return strategy
