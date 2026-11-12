"""How the integration tests are kept apart from the unit tests (ADR-0020)."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
INTEGRATION = ROOT / "tests" / "datapatchbay" / "integration"


def collect(*args: str) -> list[str]:
    """The ids of the tests that a pytest run with these arguments would run."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
        env={k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"},
    )
    return [line for line in result.stdout.splitlines() if "::" in line]


def test_plain_pytest_does_not_run_the_integration_tests():
    assert collect(str(INTEGRATION)) == []


def test_the_integration_marker_selects_every_test_of_the_integration_folder():
    files = {test.split("::")[0] for test in collect("-m", "integration", str(INTEGRATION))}
    assert files == {str(f.relative_to(ROOT)) for f in INTEGRATION.glob("test_*.py")}


def test_the_one_command_is_executable():
    assert os.access(ROOT / "scripts" / "integration-tests", os.X_OK)
