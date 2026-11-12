"""The example repo runs end to end: its DAGs run in Airflow 3 against Postgres, and roles read the output ports.

An integration test (ADR-0020). Airflow and dbt run in a container next to the Postgres container, without
datapatchbay (ADR-0001). `tests/airflow/run_example.py` runs there and asserts what each role sees.
"""

import os
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from airflow_helpers import EXAMPLE_REPO, copy_and_generate

DBT_BIN_DIR = "/opt/dbt/bin"  # the separate environment of dbt in the image


def test_example_runs_in_airflow_and_roles_read_the_output_ports(
    tmp_path: Path, run_in_airflow: Callable[..., CompletedProcess[str]]
):
    url = os.environ.get("DPB_TEST_POSTGRES_NETWORK_URL")
    if url is None:
        pytest.fail(
            "DPB_TEST_POSTGRES_NETWORK_URL is not set; run the integration tests with scripts/integration-tests"
        )
    dags = copy_and_generate(EXAMPLE_REPO, tmp_path)
    result = run_in_airflow("run_example.py", [str(dags), url, DBT_BIN_DIR], [tmp_path], network=True)
    assert result.returncode == 0, result.stdout + result.stderr
    for line in (
        "ok: a reader sees NULL in the PII column",
        "ok: a PII reader sees the value",
        "ok: a role that is not a reader cannot read the output port",
        "ok: a reader cannot read the private schema",
        "ok: dbt ran 4 data tests and all passed",  # `build_dbt` ran the real `dbt build` in the container
    ):
        assert line in result.stdout
