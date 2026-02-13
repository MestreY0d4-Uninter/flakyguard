from flakyguard.core.models import FlakyGuardConfig, FlakyTest, TestHistory, TestOutcome


def detect_flaky_tests(
    histories: list[TestHistory], config: FlakyGuardConfig
) -> list[FlakyTest]:
    flaky_tests = []

    for history in histories:
        if not history.is_flaky(config.window_size, config.threshold):
            continue

        recent_results = history.recent_results(config.window_size)

        if not recent_results:
            continue

        flaky = FlakyTest(
            test_id=history.test_id,
            flakiness_rate=history.flakiness_rate(config.window_size),
            total_runs=len(recent_results),
            failures=sum(
                1
                for r in recent_results
                if r.outcome in (TestOutcome.FAILED, TestOutcome.ERROR)
            ),
            last_seen=recent_results[-1].timestamp,
            quarantine_mode=config.quarantine_mode,
        )
        flaky_tests.append(flaky)

    return sorted(flaky_tests, key=lambda f: f.flakiness_rate, reverse=True)
