"""The generated Dagster modules, loaded and run in Dagster on an ephemeral instance and a DuckDB file (ADR-0023).

The modules of two data products are merged the way a team merges them, with a resource bound to the key `warehouse`.
"""

import importlib.util
import sys
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import duckdb
import pytest

from datapatchbay.generate import generate_repo

PRODUCT = """\
schema_version: 1
name: {name}
kind: {kind}
owner: {owner}
inputs: [{inputs}]
outputs: [{prefix}_{name}]
"""

FILES = {
    "datapatchbay.yaml": "schema_version: 1\norchestrator: dagster\nwarehouse: duckdb\nruntime: worker\n",
    "dataproducts/sa_shop/dataproduct.yaml": PRODUCT.format(
        name="shop", kind="source-aligned", owner="Jane Doe", inputs="sa_shop_private", prefix="sa"
    ),
    "dataproducts/sa_shop/inputs/sa_shop_private/port.yaml": (
        'schema_version: 1\nkind: schema\nsource: shop\nschedule: "0 5 * * *"\n'
    ),
    "dataproducts/sa_shop/inputs/sa_shop_private/ingested.yaml": """\
schema_version: 1
name: ingested_orders
columns:
  - name: order_id
    type: text
build:
  entrypoint: src/ingested.py:build
""",
    "dataproducts/sa_shop/outputs/sa_shop/port.yaml": """\
schema_version: 1
kind: schema
access:
  readers:
    - product: agg_orders
""",
    "dataproducts/sa_shop/outputs/sa_shop/orders.yaml": """\
schema_version: 1
name: orders
columns:
  - name: order_id
    type: text
    rules: [not_null]
  - name: status
    type: text
    rules:
      - rule: accepted_values
        values: [open, paid]
        severity: warning
build:
  entrypoint: src/orders.py:build
  needs: [ingested_orders]
""",
    "dataproducts/sa_shop/src/ingested.py": """\
import os

import duckdb


def build():
    with duckdb.connect(os.environ["DPB_TEST_DUCKDB"]) as db:
        db.execute("CREATE SCHEMA IF NOT EXISTS sa_shop_private")
        db.execute("CREATE OR REPLACE TABLE sa_shop_private.ingested_orders (order_id text, status text)")
        db.execute("INSERT INTO sa_shop_private.ingested_orders VALUES ('o1', 'paid'), ('o2', 'open')")
        mode = os.environ.get("DPB_TEST_MODE")
        if mode == "null_id":
            db.execute("INSERT INTO sa_shop_private.ingested_orders VALUES (NULL, 'open')")
        if mode == "bad_status":
            db.execute("INSERT INTO sa_shop_private.ingested_orders VALUES ('o3', 'lost')")
""",
    "dataproducts/sa_shop/src/orders.py": """\
import os

import duckdb


def build():
    with duckdb.connect(os.environ["DPB_TEST_DUCKDB"]) as db:
        db.execute("CREATE OR REPLACE TABLE sa_shop_private.orders AS SELECT * FROM sa_shop_private.ingested_orders")
""",
    "dataproducts/agg_orders/dataproduct.yaml": PRODUCT.format(
        name="orders", kind="aggregate", owner="Ann", inputs="sa_shop", prefix="agg"
    ),
    "dataproducts/agg_orders/inputs/sa_shop/port.yaml": "schema_version: 1\nfrom: sa_shop\n",
    "dataproducts/agg_orders/outputs/agg_orders/port.yaml": "schema_version: 1\nkind: table\n",
    "dataproducts/agg_orders/outputs/agg_orders/status_counts.yaml": """\
schema_version: 1
name: status_counts
columns:
  - name: status
    type: text
  - name: n
    type: integer
build:
  entrypoint: src/status_counts.py:build
""",
    "dataproducts/agg_orders/src/status_counts.py": """\
import os

import duckdb


def build():
    with duckdb.connect(os.environ["DPB_TEST_DUCKDB"]) as db:
        db.execute("CREATE SCHEMA IF NOT EXISTS agg_orders_private")
        db.execute(
            "CREATE OR REPLACE TABLE agg_orders_private.status_counts AS "
            "SELECT status, count(*)::integer AS n FROM sa_shop.orders GROUP BY status"
        )
""",
}


class DuckDbFile:
    """The resource of the generated modules: `get_connection()` yields a connection that commits by itself."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def get_connection(self) -> Generator[duckdb.DuckDBPyConnection]:
        connection = duckdb.connect(str(self.path))
        try:
            yield connection
        finally:
            connection.close()


@dataclass
class Project:
    dg: Any  # the dagster module
    defs: Any
    instance: Any
    database: Path
    generated: Path

    def run(self, job: str) -> Any:
        """Run a job in process on the instance; a failed run is returned, not raised."""
        return self.defs.resolve_job_def(job).execute_in_process(instance=self.instance, raise_on_error=False)

    def rows(self, query: str) -> list[tuple[Any, ...]]:
        with duckdb.connect(str(self.database)) as db:
            return db.execute(query).fetchall()

    def materialized(self, *key: str) -> bool:
        return self.instance.get_latest_materialization_event(self.dg.AssetKey(list(key))) is not None


def load_module(path: Path) -> ModuleType:
    name = f"generated_dagster_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Project]:
    """Generate the repo, load both modules and merge their definitions with the resource."""
    dg = pytest.importorskip("dagster")  # not at module level: the unit tests collect this folder without Dagster
    root = tmp_path / "repo"
    for relative, text in FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    result = generate_repo(root)
    assert result.report.ok, result.report
    generated = root / "generated"
    database = tmp_path / "warehouse.duckdb"
    monkeypatch.setenv("DPB_TEST_DUCKDB", str(database))
    modules = [load_module(generated / "sa_shop.py"), load_module(generated / "agg_orders.py")]
    defs = dg.Definitions.merge(
        *(module.defs for module in modules), dg.Definitions(resources={"warehouse": DuckDbFile(database)})
    )
    yield Project(dg, defs, dg.DagsterInstance.ephemeral(), database, generated)
    for module in modules:
        del sys.modules[module.__name__]


def test_the_merged_definitions_of_two_data_products_are_loadable(project: Project):
    project.dg.Definitions.validate_loadable(project.defs)
    keys = {key.to_user_string() for key in project.defs.resolve_all_asset_keys()}
    assert keys == {
        "sa_shop/ingested_orders",
        "sa_shop/orders",
        "sa_shop",
        "agg_orders/status_counts",
        "agg_orders",
    }
    groups = {spec.key.to_user_string(): spec.group_name for spec in project.defs.resolve_all_asset_specs()}
    assert groups["sa_shop/orders"] == "sa_shop"
    assert groups["agg_orders"] == "agg_orders"


def test_a_job_builds_the_tables_and_applies_the_output_port_views(project: Project):
    result = project.run("sa_shop")
    assert result.success
    assert project.rows("SELECT order_id, status FROM sa_shop_private.orders ORDER BY order_id") == [
        ("o1", "paid"),
        ("o2", "open"),
    ]
    assert project.rows("SELECT order_id FROM sa_shop.orders ORDER BY order_id") == [("o1",), ("o2",)]
    assert project.materialized("sa_shop")


def test_each_quality_rule_has_its_own_check_result_with_the_violation_count(project: Project):
    result = project.run("sa_shop")
    evaluations = {e.check_name: e for e in result.get_asset_check_evaluations()}
    assert sorted(evaluations) == ["accepted_values_status", "not_null_order_id"]
    assert all(e.passed for e in evaluations.values())
    assert evaluations["not_null_order_id"].metadata["violations"].value == 0


def test_a_broken_error_rule_fails_the_run_and_the_output_port_is_not_materialized(
    project: Project, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DPB_TEST_MODE", "null_id")
    result = project.run("sa_shop")
    assert not result.success
    evaluations = {e.check_name: e for e in result.get_asset_check_evaluations()}
    assert not evaluations["not_null_order_id"].passed
    assert evaluations["not_null_order_id"].severity == project.dg.AssetCheckSeverity.ERROR
    assert evaluations["not_null_order_id"].metadata["violations"].value == 1
    assert evaluations["accepted_values_status"].passed
    assert project.materialized("sa_shop", "orders")
    assert not project.materialized("sa_shop")
    with duckdb.connect(str(project.database)) as db:
        schemas = {row[0] for row in db.execute("SELECT schema_name FROM information_schema.schemata").fetchall()}
    assert "sa_shop" not in schemas


def test_a_broken_warning_rule_is_reported_and_the_run_goes_on(project: Project, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DPB_TEST_MODE", "bad_status")
    result = project.run("sa_shop")
    assert result.success
    evaluations = {e.check_name: e for e in result.get_asset_check_evaluations()}
    assert not evaluations["accepted_values_status"].passed
    assert evaluations["accepted_values_status"].severity == project.dg.AssetCheckSeverity.WARN
    assert evaluations["accepted_values_status"].metadata["violations"].value == 1
    assert project.materialized("sa_shop")


def test_the_job_has_a_running_schedule_with_the_cron_of_the_source_port_in_utc(project: Project):
    schedule = project.defs.resolve_schedule_def("sa_shop__schedule")
    assert schedule.cron_schedule == "0 5 * * *"
    assert schedule.execution_timezone == "UTC"
    assert schedule.default_status == project.dg.DefaultScheduleStatus.RUNNING
    assert schedule.job_name == "sa_shop"
    with pytest.raises(project.dg.DagsterInvariantViolationError):
        project.defs.resolve_schedule_def("agg_orders__schedule")


def test_the_reading_data_product_runs_when_the_port_it_reads_is_materialized(project: Project):
    sensor = project.defs.resolve_sensor_def("agg_orders__on_sa_shop")
    assert sensor.default_status == project.dg.DefaultSensorStatus.RUNNING
    assert sensor.job_name == "agg_orders"

    def requests(cursor: str | None) -> tuple[list[Any], str | None]:
        context = project.dg.build_sensor_context(instance=project.instance, cursor=cursor, definitions=project.defs)
        data = sensor.evaluate_tick(context)
        return list(data.run_requests), data.cursor

    assert requests(None)[0] == []
    assert project.run("sa_shop").success
    [request], cursor = requests(None)
    assert request.run_key
    assert requests(cursor)[0] == []

    assert project.run("sa_shop").success
    [second], _ = requests(cursor)
    assert second.run_key != request.run_key

    result = project.run("agg_orders")
    assert result.success
    assert project.rows("SELECT status, n FROM agg_orders_private.status_counts ORDER BY status") == [
        ("open", 1),
        ("paid", 1),
    ]
