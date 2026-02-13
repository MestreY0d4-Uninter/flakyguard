import json
import sqlite3
from datetime import datetime

from flakyguard.core.models import (
    EnvironmentInfo,
    FlakyGuardConfig,
    TestHistory,
    TestOutcome,
    TestResult,
)


class SQLiteStorage:
    def __init__(self, config: FlakyGuardConfig) -> None:
        self.db_path = config.db_path
        self._init_database()

    def _init_database(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    duration REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    env_info TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_test_id
                ON test_results(test_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON test_results(timestamp)
            """)

            cursor.execute(
                "INSERT OR IGNORE INTO metadata (key, value) VALUES (?, ?)",
                ("schema_version", "1"),
            )

            conn.commit()

    def save_result(self, result: TestResult) -> None:
        env_info_json = json.dumps({
            "python_version": result.environment_info.python_version,
            "platform": result.environment_info.platform,
            "timestamp": result.environment_info.timestamp.isoformat(),
        })

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO test_results (test_id, outcome, duration, timestamp, env_info)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    result.test_id,
                    result.outcome.value,
                    result.duration,
                    result.timestamp.isoformat(),
                    env_info_json,
                ),
            )
            conn.commit()

    def get_history(self, test_id: str, window_size: int) -> TestHistory | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT outcome, duration, timestamp, env_info
                FROM test_results
                WHERE test_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (test_id, window_size),
            )

            rows = cursor.fetchall()

        if not rows:
            return None
        results = []
        for outcome_str, duration, timestamp_str, env_info_json in reversed(rows):
            env_data = json.loads(env_info_json)
            env_info = EnvironmentInfo(
                python_version=env_data["python_version"],
                platform=env_data["platform"],
                timestamp=datetime.fromisoformat(env_data["timestamp"]),
            )

            result = TestResult(
                test_id=test_id,
                outcome=TestOutcome(outcome_str),
                duration=duration,
                timestamp=datetime.fromisoformat(timestamp_str),
                environment_info=env_info,
            )
            results.append(result)

        return TestHistory(test_id=test_id, results=tuple(results))

    def get_all_histories(self, window_size: int) -> list[TestHistory]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT test_id FROM test_results")
            test_ids = [row[0] for row in cursor.fetchall()]

        histories = []
        for test_id in test_ids:
            history = self.get_history(test_id, window_size)
            if history:
                histories.append(history)

        return histories

    def clear(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM test_results")
            conn.commit()

    def close(self) -> None:
        pass
