"""Run the generated DAGs of a repo with `warehouse: duckdb` for real, and read the result from the DuckDB file.

The integration tests run this in the Airflow container (`tests/airflow/Dockerfile`), whose Python has Airflow and its
DuckDB provider installed and not datapatchbay, so datapatchbay is not importable here (ADR-0001). It runs `airflow db
migrate` on a throwaway SQLite metadata database, points the connection `warehouse` at a DuckDB file through the
environment, and runs `dag.test()` for two DAGs. The DAG `sa_shop` builds its tables with Python, runs the audit task,
applies the views and ends with `publish_outputs`. The DAG `sa_broken` breaks a quality rule with severity `error`, so
its audit task must fail and its views must not be applied.

Usage: python run_duckdb.py DAGS_DIR DATABASE_FILE

DATABASE_FILE is created in a folder that the container may write to; the folder is mounted from the host.
The build code of the repo finds the same file through the environment variable `DPB_TEST_DUCKDB`.
"""

import json
import os
import subprocess
import sys
import tempfile

# Airflow reads its configuration when it is imported, so these come first.
AIRFLOW_HOME = tempfile.mkdtemp(prefix="patchbay-duckdb-")
os.environ["AIRFLOW_HOME"] = AIRFLOW_HOME
os.environ["AIRFLOW__CORE__LOAD_EXAMPLES"] = "False"
os.environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = f"sqlite:///{AIRFLOW_HOME}/airflow.db"

import duckdb  # noqa: E402
from airflow.dag_processing.dagbag import DagBag  # noqa: E402


def expect(actual: object, expected: object, what: str) -> None:
    assert actual == expected, f"{what}: expected {expected!r}, got {actual!r}"
    print(f"ok: {what}")


def states_of(bag: DagBag, dag_id: str) -> tuple[str, dict[str, str]]:
    """Run the DAG; return the state of the run and of each task. A task that fails does not raise here."""
    run = bag.dags[dag_id].test()
    return str(run.state), {ti.task_id: str(ti.state) for ti in run.get_task_instances()}


def main(dags_dir: str, database: str) -> None:
    dags_dir = os.path.abspath(dags_dir)
    os.environ["AIRFLOW__CORE__DAGS_FOLDER"] = dags_dir
    os.environ["DPB_TEST_DUCKDB"] = database
    # The connection `warehouse` is the one the generated DAGs name; Airflow reads it from the environment.
    os.environ["AIRFLOW_CONN_WAREHOUSE"] = json.dumps({"conn_type": "duckdb", "host": database})
    subprocess.run(["airflow", "db", "migrate"], check=True, env=os.environ, stdout=subprocess.DEVNULL)
    # `dag.test()` needs the DAGs serialized in the metadata database, which the DAG processor does in a deployment.
    subprocess.run(["airflow", "dags", "reserialize"], check=True, env=os.environ, stdout=subprocess.DEVNULL)
    bag = DagBag(dag_folder=dags_dir, safe_mode=False, bundle_path=dags_dir)
    assert not bag.import_errors, bag.import_errors

    state, tasks = states_of(bag, "sa_shop")
    expect(state, "success", "the DAG sa_shop succeeded")
    expect(
        tasks,
        {
            "build_ingested_orders": "success",
            "build_orders": "success",
            "audit_orders": "success",
            "apply_access": "success",
            "publish_outputs": "success",
        },
        "the build, audit, apply and publish tasks all succeeded",
    )

    with duckdb.connect(database, read_only=True) as db:
        expect(
            db.execute("SELECT order_id, customer_id, status FROM sa_shop.orders ORDER BY order_id").fetchall(),
            [("O-1", None, "placed"), ("O-2", None, "placed"), ("O-3", None, "placed")],
            "the view of the output port holds the rows, with NULL in the PII column",
        )
        expect(
            db.execute("SELECT count(*) FROM sa_shop_private.orders WHERE customer_id IS NOT NULL").fetchone(),
            (3,),
            "the private table keeps the PII values",
        )

    state, tasks = states_of(bag, "sa_broken")
    expect(state, "failed", "a broken rule with severity error fails the DAG sa_broken")
    expect(tasks["build_orders"], "success", "the table of sa_broken was built")
    expect(tasks["audit_orders"], "failed", "the audit task of sa_broken failed")
    expect(tasks["apply_access"], "upstream_failed", "the views of sa_broken were not applied")
    with duckdb.connect(database, read_only=True) as db:
        expect(
            db.execute("SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'sa_broken'").fetchone(),
            (0,),
            "the output port of sa_broken does not exist",
        )


if __name__ == "__main__":
    main(*sys.argv[1:])
