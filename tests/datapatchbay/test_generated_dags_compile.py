"""Every DAG file generated for the fixture repo and the example repo is valid Python, without Airflow.

Loading the DAGs in Airflow is an integration test (ADR-0020), so this is what keeps a syntax error in generated code
failing CI. The Airflow image of the integration tests also must not hold datapatchbay (ADR-0001).
"""

from pathlib import Path

import pytest
from airflow_helpers import (
    DUCKDB_DAGS,
    DUCKDB_REPO,
    EXAMPLE_DAGS,
    EXAMPLE_REPO,
    FIXTURE_DAGS,
    FIXTURE_REPO,
    ROOT,
    copy_and_generate,
)


@pytest.mark.parametrize(
    ("repo", "dag_ids"),
    [
        pytest.param(FIXTURE_REPO, FIXTURE_DAGS, id="fixture"),
        pytest.param(EXAMPLE_REPO, EXAMPLE_DAGS, id="example"),
        pytest.param(DUCKDB_REPO, DUCKDB_DAGS, id="duckdb"),
    ],
)
def test_every_generated_dag_file_compiles(repo: Path, dag_ids: dict[str, str], tmp_path: Path):
    dags = copy_and_generate(repo, tmp_path)
    files = sorted(dags.glob("*.py"))
    assert [file.stem for file in files] == sorted(dag_ids)
    for file in files:
        compile(file.read_text(), str(file), "exec")


def test_the_airflow_image_pins_airflow_once_and_does_not_install_datapatchbay():
    dockerfile = (ROOT / "tests" / "airflow" / "Dockerfile").read_text()
    pins = [line for line in dockerfile.splitlines() if "AIRFLOW_VERSION=" in line]
    assert len(pins) == 1
    assert "pip install datapatchbay" not in dockerfile.lower()
    assert "datapatchbay" not in "".join(line for line in dockerfile.splitlines() if not line.startswith("#"))
