from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class TestOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class QuarantineMode(str, Enum):
    WARN = "warn"
    SKIP = "skip"
    RETRY = "retry"


class EnvironmentInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    python_version: str
    platform: str
    timestamp: datetime


class TestResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    test_id: str
    outcome: TestOutcome
    duration: float = Field(ge=0.0)
    timestamp: datetime
    environment_info: EnvironmentInfo


class TestHistory(BaseModel):
    model_config = ConfigDict(frozen=True)

    test_id: str
    results: tuple[TestResult, ...]

    def recent_results(self, window_size: int) -> tuple[TestResult, ...]:
        return self.results[-window_size:] if window_size > 0 else self.results

    def flakiness_rate(self, window_size: int) -> float:
        if not self.results:
            return 0.0

        recent = self.recent_results(window_size)
        if not recent:
            return 0.0

        failures = sum(
            1 for r in recent if r.outcome in (TestOutcome.FAILED, TestOutcome.ERROR)
        )
        return failures / len(recent)

    def is_flaky(self, window_size: int, threshold: float) -> bool:
        if len(self.results) < 2:
            return False

        recent = self.recent_results(window_size)
        if len(recent) < 2:
            return False

        has_success = any(r.outcome == TestOutcome.PASSED for r in recent)
        has_failure = any(
            r.outcome in (TestOutcome.FAILED, TestOutcome.ERROR) for r in recent
        )

        if not (has_success and has_failure):
            return False

        return self.flakiness_rate(window_size) > threshold


class FlakyTest(BaseModel):
    model_config = ConfigDict(frozen=True)

    test_id: str
    flakiness_rate: float = Field(ge=0.0, le=1.0)
    total_runs: int = Field(ge=0)
    failures: int = Field(ge=0)
    last_seen: datetime
    quarantine_mode: QuarantineMode | None = None


class FlakyGuardConfig(BaseModel):
    window_size: int = Field(default=50, ge=1)
    threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    quarantine_mode: QuarantineMode = Field(default=QuarantineMode.WARN)
    db_path: Path = Field(default=Path(".flakyguard/history.db"))
    retry_count: int = Field(default=3, ge=1)
