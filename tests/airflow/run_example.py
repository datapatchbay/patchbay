"""Run the generated DAGs of the example repo for real, against a Postgres, and read the result as two kinds of reader.

CI runs this with the Python of the separate virtual environment that has Airflow and its Postgres provider installed,
never the project's environment, so datapatchbay is not importable here (ADR-0001). It runs `airflow db migrate` on a
throwaway SQLite metadata database, points the connection `warehouse` at Postgres through the environment, and runs
`dag.test()` for the source-aligned DAG and then for the aggregate DAG. Each DAG builds its tables, runs the audit
tasks and applies the views and grants. Roles are expected to exist (ADR-0017), so the script creates them first.

Usage: python run_example.py DAGS_DIR POSTGRES_URL

POSTGRES_URL names a server where the user may create roles and databases. The script works in a database of its own and
drops it at the end. The roles are created by the script and dropped at the end too.
"""

import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Generator
from contextlib import contextmanager
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


def run_dag(bag: DagBag, dag_id: str) -> None:
    dag = bag.dags[dag_id]
    run = dag.test()
    states = {task_instance.task_id: str(task_instance.state) for task_instance in run.get_task_instances()}
    failed = {task_id: state for task_id, state in states.items() if state != "success"}
    assert str(run.state) == "success", f"DAG {dag_id} ended {run.state}: {states}"
    assert not failed, f"DAG {dag_id} has tasks that did not succeed: {failed}"
    print(f"DAG {dag_id}: {', '.join(sorted(states))}")


def expect(actual: object, expected: object, what: str) -> None:
    assert actual == expected, f"{what}: expected {expected!r}, got {actual!r}"
    print(f"ok: {what}")


def main(dags_dir: str, admin_url: str) -> None:
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
        subprocess.run(["airflow", "db", "migrate"], check=True, env=os.environ, stdout=subprocess.DEVNULL)
        # `dag.test()` needs the DAGs serialized in the metadata database, which the DAG processor does in a deployment.
        subprocess.run(["airflow", "dags", "reserialize"], check=True, env=os.environ, stdout=subprocess.DEVNULL)

        bag = DagBag(dag_folder=dags_dir, safe_mode=False, bundle_path=dags_dir)
        assert not bag.import_errors, bag.import_errors
        run_dag(bag, "sa_ilab_orders")
        run_dag(bag, "agg_lab_turnaround")

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
