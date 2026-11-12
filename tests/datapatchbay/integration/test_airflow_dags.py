"""The generated DAGs of the fixture repo and of the example repo load in Airflow 3. An integration test (ADR-0020).

Airflow runs in a container without datapatchbay (ADR-0001): the DAGs are generated here and mounted into it.
"""

from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from airflow_helpers import EXAMPLE_DAGS, EXAMPLE_REPO, FIXTURE_DAGS, FIXTURE_REPO, copy_and_generate


@pytest.mark.parametrize(
    ("repo", "expected"),
    [pytest.param(FIXTURE_REPO, FIXTURE_DAGS, id="fixture"), pytest.param(EXAMPLE_REPO, EXAMPLE_DAGS, id="example")],
)
def test_generated_dags_load_in_airflow(
    repo: Path, expected: dict[str, str], tmp_path: Path, run_in_airflow: Callable[..., CompletedProcess[str]]
):
    dags = copy_and_generate(repo, tmp_path)
    expectations = [part for dag_id, tasks in expected.items() for part in (dag_id, tasks)]
    result = run_in_airflow("check_dags.py", [str(dags), *expectations], [tmp_path])
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"loaded {len(expected)} DAG(s)" in result.stdout
