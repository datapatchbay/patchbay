"""Load generated DAG files in Airflow 3 and fail on any import error.

The integration tests run this in the Airflow container (`tests/airflow/Dockerfile`), never in the project's
environment: Airflow is not a dependency of datapatchbay, and datapatchbay is not installed there, which also shows that
a generated file stands alone (ADR-0001).

Usage: python check_dags.py DAGS_DIR [DAG_ID TASK_ID,TASK_ID ...]

Every DAG file must load. Each DAG_ID given must exist with exactly the listed tasks.
"""

import os
import sys
import tempfile

# Airflow reads its configuration when it is imported, so these come first.
os.environ["AIRFLOW__CORE__LOAD_EXAMPLES"] = "False"
os.environ.setdefault("AIRFLOW_HOME", tempfile.mkdtemp(prefix="patchbay-airflow-"))

from airflow.dag_processing.dagbag import DagBag


def main(argv: list[str]) -> int:
    dags_dir, *expectations = argv
    # safe_mode=False parses every file, including one that does not mention "airflow" and "dag".
    bag = DagBag(dag_folder=dags_dir, safe_mode=False, bundle_path=dags_dir)
    failures = [f"import error in {path}: {error}" for path, error in sorted(bag.import_errors.items())]
    for dag_id, tasks in zip(expectations[::2], expectations[1::2], strict=True):
        dag = bag.dags.get(dag_id)
        if dag is None:
            failures.append(f"DAG {dag_id!r} was not loaded")
        elif sorted(dag.task_ids) != sorted(tasks.split(",")):
            failures.append(f"DAG {dag_id!r} has tasks {sorted(dag.task_ids)}, expected {sorted(tasks.split(','))}")
    for failure in failures:
        print(failure, file=sys.stderr)
    print(f"loaded {len(bag.dags)} DAG(s): {', '.join(sorted(bag.dags))}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
