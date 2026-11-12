"""A data product on DuckDB runs end to end in Airflow 3. An integration test (ADR-0020).

Airflow runs in a container without datapatchbay (ADR-0001), reaching DuckDB through its own connection `warehouse`.
`tests/airflow/run_duckdb.py` runs there and asserts what the DuckDB file holds afterwards. No Postgres is involved.
"""

from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

from airflow_helpers import DUCKDB_REPO, copy_and_generate


def test_duckdb_dags_run_in_airflow_and_a_broken_rule_fails_the_run(
    tmp_path: Path, run_in_airflow: Callable[..., CompletedProcess[str]]
):
    dags = copy_and_generate(DUCKDB_REPO, tmp_path)
    warehouse = tmp_path / "warehouse"  # the DuckDB file lives in a volume that the container may write to
    warehouse.mkdir()
    result = run_in_airflow(
        "run_duckdb.py", [str(dags), str(warehouse / "shop.duckdb")], [tmp_path], writable=[warehouse]
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for line in (
        "ok: the build, audit, apply and publish tasks all succeeded",
        "ok: the view of the output port holds the rows, with NULL in the PII column",
        "ok: a broken rule with severity error fails the DAG sa_broken",
        "ok: the views of sa_broken were not applied",
    ):
        assert line in result.stdout
    assert (warehouse / "shop.duckdb").exists()
