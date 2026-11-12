"""Run the generated DAGs of the example repo for real, against a Postgres, and read the result as two kinds of reader.

CI runs this with the Python of the separate virtual environment that has Airflow and its Postgres provider installed,
never the project's environment, so datapatchbay is not importable here (ADR-0001). It runs `airflow db migrate` on a
throwaway SQLite metadata database, points the connection `warehouse` at Postgres through the environment, and runs
`dag.test()` for the source-aligned DAG and then for the aggregate DAG. The source-aligned DAG builds its tables with
Python, runs the audit tasks and applies the views and grants. The aggregate DAG is built by dbt: its `build_dbt` task
runs the real `dbt build` of the example's dbt project, which builds the model from the output port of the other data
product and runs its data tests, and then the DAG applies the views and grants. Roles are expected to exist
(ADR-0017), so the script creates them first.

Usage: python run_example.py DAGS_DIR POSTGRES_URL [DBT_BIN_DIR]

The `build_dbt` task runs the `dbt` command of its PATH. dbt cannot be installed next to Airflow (their pins conflict),
so DBT_BIN_DIR names the `bin` folder of the environment that has dbt; it is put first in the PATH. dbt reads the
connection from the environment in the profile of the example, which this script sets from POSTGRES_URL.

POSTGRES_URL names a server where the user may create roles and databases. The script works in a database of its own and
drops it at the end. The roles are created by the script and dropped at the end too.
"""

import json
import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

# Airflow reads its configuration when it is imported, so these come first.
AIRFLOW_HOME = tempfile.mkdtemp(prefix="patchbay-example-")
os.environ["AIRFLOW_HOME"] = AIRFLOW_HOME
os.environ["AIRFLOW__CORE__LOAD_EXAMPLES"] = "False"
os.environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = f"sqlite:///{AIRFLOW_HOME}/airflow.db"

import psycopg2  # noqa: E402  # ty: ignore[import-not-found]
from airflow.dag_processing.dagbag import DagBag  # noqa: E402  # ty: ignore[import-not-found]

REPORTER = "grp-lab-reporting"
DOCTOR = "grp-lab-doctors"
MANAGER = "grp-lab-management"
OUTSIDER = "grp-outsider"
DATA_PRODUCT_ROLE = "dp_agg_lab_turnaround"
ROLES = (REPORTER, DOCTOR, MANAGER, OUTSIDER, DATA_PRODUCT_ROLE)


def with_database(url: str, database: str) -> str:
    return urlunsplit(urlsplit(url)._replace(path=f"/{database}"))


@contextmanager
def connect(url: str) -> Generator[Any]:
    connection = psycopg2.connect(url)
    connection.autocommit = True
    try:
        yield connection
    finally:
        connection.close()


def query(url: str, role: str | None, statement: str) -> list[tuple]:
    """Run a query like a user with `role` would, and return its rows."""
    with connect(url) as connection, connection.cursor() as cursor:
        if role:
            cursor.execute(f'SET ROLE "{role}"')
        cursor.execute(statement)
        return cursor.fetchall()


def run_dag(bag: DagBag, dag_id: str, expected_tasks: set[str]) -> None:
    dag = bag.dags[dag_id]
    run = dag.test()
    states = {task_instance.task_id: str(task_instance.state) for task_instance in run.get_task_instances()}
    failed = {task_id: state for task_id, state in states.items() if state != "success"}
    assert str(run.state) == "success", f"DAG {dag_id} ended {run.state}: {states}"
    assert set(states) == expected_tasks, f"DAG {dag_id} ran {sorted(states)}, expected {sorted(expected_tasks)}"
    assert not failed, f"DAG {dag_id} has tasks that did not succeed: {failed}"
    print(f"DAG {dag_id}: {', '.join(sorted(states))}")


def expect(actual: object, expected: object, what: str) -> None:
    assert actual == expected, f"{what}: expected {expected!r}, got {actual!r}"
    print(f"ok: {what}")


def point_dbt_at(url: str, dbt_bin_dir: str | None) -> Path:
    """Set what `dbt build` reads in the profile of the example; return the folder for its artifacts."""
    parts = urlsplit(url)
    os.environ.update(
        PGHOST=parts.hostname or "localhost",
        PGPORT=str(parts.port or 5432),
        PGUSER=parts.username or "",
        PGPASSWORD=parts.password or "",
        PGDATABASE=parts.path.lstrip("/"),
    )
    # dbt writes its artifacts next to the project by default; keep the working tree of the example clean.
    artifacts = Path(AIRFLOW_HOME) / "dbt"
    os.environ["DBT_TARGET_PATH"] = str(artifacts / "target")
    os.environ["DBT_LOG_PATH"] = str(artifacts / "logs")
    if dbt_bin_dir:
        os.environ["PATH"] = f"{os.path.abspath(dbt_bin_dir)}{os.pathsep}{os.environ['PATH']}"
    return artifacts


def check_dbt_tests(artifacts: Path) -> None:
    """The model was built and its data tests ran and passed, so a build that skipped them cannot go unnoticed."""
    results = json.loads((artifacts / "target" / "run_results.json").read_text())["results"]
    statuses = {tuple(r["unique_id"].split(".")[::2]): r["status"] for r in results}  # (resource type, name) -> status
    models = sorted(name for kind, name in statuses if kind == "model")
    tests = {name: status for (kind, name), status in statuses.items() if kind == "test"}
    expect(models, ["agg_lab_turnaround__turnaround"], "dbt built the model")
    assert len(tests) == 4, f"expected 4 data tests: {tests}"  # three column tests and the row_count rule
    assert set(tests.values()) == {"pass"}, tests
    print(f"ok: dbt ran {len(tests)} data tests and all passed")


def main(dags_dir: str, admin_url: str, dbt_bin_dir: str | None = None) -> None:
    dags_dir = os.path.abspath(dags_dir)
    os.environ["AIRFLOW__CORE__DAGS_FOLDER"] = dags_dir
    database = f"dpb_example_{uuid.uuid4().hex[:12]}"
    with connect(admin_url) as admin, admin.cursor() as cursor:
        cursor.execute(f'CREATE DATABASE "{database}"')
        for role in ROLES:
            cursor.execute(f'DROP ROLE IF EXISTS "{role}"')
            cursor.execute(f'CREATE ROLE "{role}"')
    url = with_database(admin_url, database)
    try:
        # The connection `warehouse` is the one the generated DAGs name; Airflow reads it from the environment.
        os.environ["AIRFLOW_CONN_WAREHOUSE"] = url.replace("postgresql://", "postgres://", 1)
        artifacts = point_dbt_at(url, dbt_bin_dir)
        subprocess.run(["airflow", "db", "migrate"], check=True, env=os.environ, stdout=subprocess.DEVNULL)
        # `dag.test()` needs the DAGs serialized in the metadata database, which the DAG processor does in a deployment.
        subprocess.run(["airflow", "dags", "reserialize"], check=True, env=os.environ, stdout=subprocess.DEVNULL)

        bag = DagBag(dag_folder=dags_dir, safe_mode=False, bundle_path=dags_dir)
        assert not bag.import_errors, bag.import_errors
        # The audit and the access grants are tasks of the DAG, so a missing one fails here instead of passing silently.
        run_dag(
            bag,
            "sa_ilab_orders",
            {"build_ingested_orders", "build_orders", "audit_orders", "apply_access", "publish_outputs"},
        )
        # The rules of the dbt table are data tests inside `build_dbt`, so this DAG has no audit task.
        run_dag(bag, "agg_lab_turnaround", {"build_dbt", "apply_access", "publish_outputs"})
        check_dbt_tests(artifacts)

        orders = "SELECT order_id, patient_id FROM sa_ilab_orders.orders ORDER BY order_id"
        expect(
            query(url, REPORTER, orders),
            [("LO-1", None), ("LO-2", None), ("LO-3", None)],
            "a reader sees NULL in the PII column",
        )
        expect(
            query(url, DOCTOR, orders),
            [("LO-1", "P-100"), ("LO-2", "P-101"), ("LO-3", "P-102")],
            "a PII reader sees the value",
        )
        expect(
            query(url, DATA_PRODUCT_ROLE, "SELECT count(*) FROM sa_ilab_orders.orders"),
            [(3,)],
            "the aggregate data product's role reads the output port",
        )
        expect(
            query(url, MANAGER, "SELECT order_id, turnaround_hours FROM agg_lab_turnaround.turnaround ORDER BY 1"),
            [("LO-1", 48), ("LO-2", 24)],
            "a reader of the aggregate reads its output port",
        )
        for role, statement, what in (
            (
                OUTSIDER,
                "SELECT 1 FROM sa_ilab_orders.orders",
                "a role that is not a reader cannot read the output port",
            ),
            (REPORTER, "SELECT 1 FROM sa_ilab_orders_private.orders", "a reader cannot read the private schema"),
        ):
            try:
                query(url, role, statement)
            except psycopg2.errors.InsufficientPrivilege:
                print(f"ok: {what}")
            else:
                raise AssertionError(what)
    finally:
        with connect(admin_url) as admin, admin.cursor() as cursor:
            cursor.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
            for role in ROLES:
                cursor.execute(f'DROP ROLE IF EXISTS "{role}"')


if __name__ == "__main__":
    main(*sys.argv[1:])
