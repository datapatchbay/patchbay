"""Constants and helpers shared by the Airflow integration tests."""

import shutil
from pathlib import Path

from datapatchbay.generate import generate_repo

ROOT = Path(__file__).parents[2]
FIXTURE_REPO = ROOT / "tests" / "airflow" / "repo"
EXAMPLE_REPO = ROOT / "examples" / "jaffle_shop"
DUCKDB_REPO = ROOT / "tests" / "airflow" / "duckdb_repo"

# DAG id -> its task ids, for every DAG the repo generates
FIXTURE_DAGS = {
    "sa_jaffle_orders": "apply_access,audit_orders,build_ingested_orders,build_orders,publish_outputs",
    "agg_order_turnaround": "apply_access,build_turnaround,publish_outputs",
    "agg_weekly_orders": "apply_access,build_weekly_raw,build_weekly,build_weekly_pod,build_dbt,publish_outputs",
}
EXAMPLE_DAGS = {
    "sa_jaffle_orders": "apply_access,audit_orders,build_ingested_orders,build_orders,publish_outputs",
    "agg_order_turnaround": "apply_access,build_dbt,publish_outputs",
}


def copy_and_generate(repo: Path, work: Path) -> Path:
    """Copy the repo, so that generating changes nothing in the working tree; return the folder of its generated DAGs.

    A generated worker task finds its data product folder relative to the DAG file, so the container gets `work` at
    the same path as the host.
    """
    copy = work / "repo"
    shutil.copytree(repo, copy, ignore=shutil.ignore_patterns("target", "generated", "__pycache__"))
    dags = work / "dags"
    generate_repo(copy, output_dir=dags)
    return dags
