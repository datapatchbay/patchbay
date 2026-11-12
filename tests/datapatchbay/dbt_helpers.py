"""Constants and helpers shared by the dbt tests."""

import shutil
import subprocess
from pathlib import Path

import pytest

from datapatchbay.plugins import PlannedRepo
from datapatchbay.problems import Report
from datapatchbay.validation import plan_repo, validate_repo

DP = "dataproducts/agg_order_turnaround"
TABLE = f"{DP}/outputs/agg_order_turnaround/turnaround.yaml"
MODEL = f"{DP}/models/agg_order_turnaround__turnaround.sql"
TABLE_YAML = "schema_version: 1\nname: turnaround\ncolumns:\n  - name: days\n    type: numeric\n"


def rendered(repo: Path) -> list[str]:
    """The problems of `validate_repo`, with an empty dbt manifest in place unless the test made one."""
    if not (repo / "target" / "manifest.json").exists():
        write(repo, "target/manifest.json", '{"metadata": {}, "nodes": {}, "sources": {}}')
    return [problem.render() for problem in validate_repo(repo).problems]


def checked(repo: Path) -> list[str]:
    """The problems of the files themselves, before `validate_repo` compares the generated dbt files."""
    result = plan_repo(repo)
    return [problem.render() for problem in result.problems] if isinstance(result, Report) else []


def planned(repo: Path) -> PlannedRepo:
    """The planned repo, which must have passed the gate."""
    result = plan_repo(repo)
    assert isinstance(result, PlannedRepo), [problem.render() for problem in result.problems]
    return result


def write(repo: Path, relative: str, text: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


PROFILES = (
    "jaffle_shop:\n  target: dev\n  outputs:\n    dev:\n"
    "      {type: postgres, host: localhost, user: u, password: p, port: 5432, dbname: d, schema: s, threads: 1}\n"
)


def dbt_parse(project: Path, profiles_dir: Path) -> None:
    """Run the real `dbt parse` on the project, which writes `target/manifest.json`.

    For the integration tests only. dbt is in the dependency group `dbt`, which `scripts/integration-tests` installs,
    so a missing dbt fails the test: a selected integration test must run (ADR-0020).
    """
    dbt = shutil.which("dbt")
    if dbt is None:
        pytest.fail("dbt is not installed; run the integration tests with scripts/integration-tests")
    result = subprocess.run(
        [dbt, "parse", "--project-dir", str(project), "--profiles-dir", str(profiles_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
