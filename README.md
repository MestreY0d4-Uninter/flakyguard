# FlakyGuard 🛡️

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**Zero-config pytest plugin to detect, track, and manage flaky tests**

Flaky tests are one of the biggest frustrations in software development. FlakyGuard automatically detects unstable tests, tracks their history, and helps you quarantine them until they're fixed.

## Features

- 🔍 **Automatic Detection**: Statistical analysis identifies flaky tests across test runs
- 📊 **Historical Tracking**: SQLite-based persistence maintains test result history
- 🎯 **Quarantine Modes**: Warn, skip, or retry flaky tests to prevent CI failures
- 📈 **Rich Reports**: Beautiful terminal output with detailed flakiness metrics
- ⚙️ **Zero Configuration**: Works out-of-the-box with sensible defaults
- 🚀 **Minimal Overhead**: Lightweight integration with pytest hooks

## Installation

```bash
pip install flakyguard
```

Or with `uv`:

```bash
uv add flakyguard
```

## Quick Start

### 1. Enable FlakyGuard in your pytest runs

```bash
pytest --flakyguard
```

That's it! FlakyGuard will now track all test results.

### 2. Run tests multiple times to build history

```bash
# Run your test suite multiple times
pytest --flakyguard
pytest --flakyguard
pytest --flakyguard
```

### 3. View flaky test report

```bash
flakyguard report
```

Example output:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Test ID                  ┃ Flakiness   ┃ Failures ┃ Total Runs ┃ Last Seen   ┃ Quarantine ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ tests/test_api.py::...   │      25.0%  │       15 │         60 │  2026-02-12 │    warn    │
│ tests/test_db.py::...    │      12.5%  │        5 │         40 │  2026-02-12 │    warn    │
└──────────────────────────┴─────────────┴──────────┴────────────┴─────────────┴────────────┘
```

## Configuration

### Command-line Options

```bash
pytest --flakyguard \
    --flakyguard-mode=warn \         # Quarantine mode: warn, skip, or retry
    --flakyguard-threshold=0.05 \    # Flakiness threshold (5%)
    --flakyguard-window=50 \         # Analysis window size
    --flakyguard-db=.flakyguard/history.db  # Database path
```

### Quarantine Modes

**warn** (default): Mark flaky tests with `xfail` but let them run normally

```bash
pytest --flakyguard --flakyguard-mode=warn
```

**skip**: Skip flaky tests entirely to prevent CI failures

```bash
pytest --flakyguard --flakyguard-mode=skip
```

**retry**: Automatically retry flaky tests up to N times

```bash
pytest --flakyguard --flakyguard-mode=retry --flakyguard-retry-count=3
```

### Configuration File

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = [
    "--flakyguard",
    "--flakyguard-mode=warn",
    "--flakyguard-threshold=0.05",
    "--flakyguard-window=50",
]
```

## CLI Commands

### `flakyguard report`

Show detailed report with tables and summaries:

```bash
flakyguard report
flakyguard report --db=custom.db --threshold=0.1
```

### `flakyguard list`

Quick list of flaky tests:

```bash
flakyguard list
```

Output:

```
Found 3 flaky test(s):
  - tests/test_api.py::test_request (25.0%)
  - tests/test_db.py::test_connection (12.5%)
  - tests/test_cache.py::test_invalidation (8.3%)
```

### `flakyguard clear`

Clear test history database:

```bash
flakyguard clear
flakyguard clear --force  # Skip confirmation
```

## How It Works

### Detection Algorithm

FlakyGuard uses statistical analysis to detect flaky tests:

1. **Track Results**: Every test run is recorded with outcome (passed/failed/error)
2. **Analyze History**: Within a sliding window (default: 50 runs), calculate failure rate
3. **Detect Flakiness**: If a test has BOTH successes AND failures, and failure rate > threshold (default: 5%), it's marked as flaky
4. **Quarantine**: Apply the selected strategy (warn/skip/retry) to flaky tests

### Example

```
Test runs:  P P P F P P F P P P  (P=passed, F=failed)
            └─────────┬─────────┘
                   window=10

Failure rate: 2/10 = 20%
Threshold: 5%
Has both P and F: Yes
Result: FLAKY ⚠️
```

### Why "Both Successes and Failures"?

- Tests that **always pass** are stable ✅
- Tests that **always fail** are broken (not flaky) ❌
- Tests that **sometimes pass, sometimes fail** are flaky ⚠️

This prevents false positives from genuinely broken tests.

## Best Practices

### 1. Build History Gradually

Run your test suite at least 10-20 times before relying on flaky test detection. More runs = more accurate statistics.

### 2. Tune the Threshold

- **High threshold (10-20%)**: Detect only very unstable tests
- **Low threshold (2-5%)**: Detect subtle flakiness early
- **Default (5%)**: Good balance for most projects

### 3. Integrate into CI

```yaml
# .github/workflows/test.yml
- name: Run tests with FlakyGuard
  run: pytest --flakyguard --flakyguard-mode=warn

- name: Generate flaky test report
  if: always()
  run: flakyguard report
```

### 4. Fix, Don't Just Skip

Quarantine modes help prevent CI failures, but the goal is to **fix flaky tests**, not hide them forever.

Use FlakyGuard reports to:
- Identify the most problematic tests (highest flakiness rate)
- Track trends over time
- Measure improvement after fixes

## Architecture

FlakyGuard follows a clean hexagonal architecture:

```
src/flakyguard/
├── core/           # Domain logic
│   ├── models.py       # Data models (Pydantic)
│   ├── detector.py     # Flakiness detection algorithm
│   └── quarantine.py   # Quarantine strategies
├── adapters/       # Infrastructure
│   └── storage.py      # SQLite persistence
├── ports/          # Interfaces
│   └── protocols.py    # Port contracts (Protocol)
├── plugin.py       # Pytest plugin (hooks)
├── reporter.py     # Rich terminal output
└── cli.py          # Standalone CLI
```

## Development

### Setup

```bash
git clone https://github.com/MestreY0d4-Uninter/flakyguard.git
cd flakyguard

# Install dependencies
uv sync
```

### Run Tests

```bash
uv run pytest tests/unit -v
uv run pytest tests/integration -v
```

### Quality Checks

```bash
uv run ruff check .
uv run mypy .
uv run pyright
uv run coverage run --branch -m pytest
uv run coverage report -m
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- Built with [pytest](https://pytest.org/)
- Terminal UI powered by [Rich](https://rich.readthedocs.io/)
- Data validation with [Pydantic](https://pydantic-docs.helpmanual.io/)

---

**Made with ❤️ for developers frustrated by flaky tests**
