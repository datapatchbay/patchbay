"""The generated Dagster modules, loaded and run in real Dagster (ADR-0023). Integration tests (ADR-0020).

The data products have the names of the how-to, and the tests run the fenced Python blocks of `docs/howto/dagster.md`:
the definitions file with `DuckDBResource` and the `PostgresResource`. Runs are in process on an ephemeral instance.
The Postgres tests and the dbt test need the Postgres of `scripts/integration-tests`.
"""

import importlib.util
import os
import re
import shutil
import sys
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlparse

import duckdb
import psycopg
import pytest
from psycopg import sql

from datapatchbay.generate import generate_repo

ROOT = Path(__file__).parents[3]
DOC = ROOT / "docs" / "howto" / "dagster.md"
MACRO = ROOT / "examples" / "jaffle_shop" / "macros" / "generate_schema_name.sql"

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
    "dataproducts/sa_jaffle_orders/dataproduct.yaml": PRODUCT.format(
        name="jaffle_orders", kind="source-aligned", owner="Jane Doe", inputs="sa_jaffle_orders_private", prefix="sa"
    ),
    "dataproducts/sa_jaffle_orders/inputs/sa_jaffle_orders_private/port.yaml": (
        'schema_version: 1\nkind: schema\nsource: shop\nschedule: "0 5 * * *"\n'
    ),
    "dataproducts/sa_jaffle_orders/inputs/sa_jaffle_orders_private/ingested.yaml": """\
schema_version: 1
name: ingested_orders
columns:
  - name: order_id
    type: text
build:
  entrypoint: src/ingested.py:build
""",
    "dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/port.yaml": """\
schema_version: 1
kind: schema
access:
  readers:
    - product: agg_order_turnaround
""",
    "dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/orders.yaml": """\
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
    "dataproducts/sa_jaffle_orders/src/ingested.py": """\
import os

import duckdb


def build():
    with duckdb.connect(os.environ["DPB_TEST_DUCKDB"]) as db:
        db.execute("CREATE SCHEMA IF NOT EXISTS sa_jaffle_orders_private")
        db.execute("CREATE OR REPLACE TABLE sa_jaffle_orders_private.ingested_orders (order_id text, status text)")
        db.execute("INSERT INTO sa_jaffle_orders_private.ingested_orders VALUES ('o1', 'paid'), ('o2', 'open')")
        mode = os.environ.get("DPB_TEST_MODE")
        if mode == "null_id":
            db.execute("INSERT INTO sa_jaffle_orders_private.ingested_orders VALUES (NULL, 'open')")
        if mode == "bad_status":
            db.execute("INSERT INTO sa_jaffle_orders_private.ingested_orders VALUES ('o3', 'lost')")
""",
    "dataproducts/sa_jaffle_orders/src/orders.py": """\
import os

import duckdb


def build():
    with duckdb.connect(os.environ["DPB_TEST_DUCKDB"]) as db:
        db.execute(
            "CREATE OR REPLACE TABLE sa_jaffle_orders_private.orders AS "
            "SELECT * FROM sa_jaffle_orders_private.ingested_orders"
        )
""",
    "dataproducts/agg_order_turnaround/dataproduct.yaml": PRODUCT.format(
        name="order_turnaround", kind="aggregate", owner="Ann", inputs="sa_jaffle_orders", prefix="agg"
    ),
    "dataproducts/agg_order_turnaround/inputs/sa_jaffle_orders/port.yaml": (
        "schema_version: 1\nfrom: sa_jaffle_orders\n"
    ),
    "dataproducts/agg_order_turnaround/outputs/agg_order_turnaround/port.yaml": "schema_version: 1\nkind: table\n",
    "dataproducts/agg_order_turnaround/outputs/agg_order_turnaround/status_counts.yaml": """\
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
    "dataproducts/agg_order_turnaround/src/status_counts.py": """\
import os

import duckdb


def build():
    with duckdb.connect(os.environ["DPB_TEST_DUCKDB"]) as db:
        db.execute("CREATE SCHEMA IF NOT EXISTS agg_order_turnaround_private")
        db.execute(
            "CREATE OR REPLACE TABLE agg_order_turnaround_private.status_counts AS "
            "SELECT status, count(*)::integer AS n FROM sa_jaffle_orders.orders GROUP BY status"
        )
""",
}


POSTGRES_SOURCES = {
    "datapatchbay.yaml": "schema_version: 1\norchestrator: dagster\nwarehouse: postgres\nruntime: worker\n",
    "dataproducts/sa_jaffle_orders/src/ingested.py": """\
import os

import psycopg


def build():
    with psycopg.connect(os.environ["WAREHOUSE_URL"], autocommit=True) as db:
        db.execute("CREATE SCHEMA IF NOT EXISTS sa_jaffle_orders_private")
        db.execute("DROP TABLE IF EXISTS sa_jaffle_orders_private.ingested_orders")
        db.execute("CREATE TABLE sa_jaffle_orders_private.ingested_orders (order_id text, status text)")
        db.execute("INSERT INTO sa_jaffle_orders_private.ingested_orders VALUES ('o1', 'paid'), ('o2', 'open')")
""",
    "dataproducts/sa_jaffle_orders/src/orders.py": """\
import os

import psycopg


def build():
    with psycopg.connect(os.environ["WAREHOUSE_URL"], autocommit=True) as db:
        db.execute("DROP TABLE IF EXISTS sa_jaffle_orders_private.orders")
        db.execute("CREATE TABLE sa_jaffle_orders_private.orders AS "
            "SELECT * FROM sa_jaffle_orders_private.ingested_orders")
""",
}

ROLES = ("dp_sa_jaffle_orders", "dp_agg_order_turnaround", "dp_agg_order_dbt")

DBT_FILES = {
    "datapatchbay.yaml": "schema_version: 1\norchestrator: dagster\nwarehouse: postgres\nruntime: worker\n",
    "dbt_project.yml": (
        "name: dpb_dagster\nversion: '1.0'\nprofile: dpb_dagster\nmacro-paths: [macros]\n"
        "model-paths: [dataproducts/agg_order_dbt/models]\n"
    ),
    "dataproducts/agg_order_dbt/dataproduct.yaml": (
        "schema_version: 1\nname: order_dbt\nkind: aggregate\nowner: Ann\noutputs: [agg_order_dbt]\n"
    ),
    "dataproducts/agg_order_dbt/outputs/agg_order_dbt/port.yaml": "schema_version: 1\nkind: schema\n",
    "dataproducts/agg_order_dbt/outputs/agg_order_dbt/raw.yaml": """\
schema_version: 1
name: raw
columns:
  - name: id
    type: integer
build:
  entrypoint: src/raw.py:build
""",
    "dataproducts/agg_order_dbt/outputs/agg_order_dbt/totals.yaml": """\
schema_version: 1
name: totals
columns:
  - name: n
    type: integer
build:
  executor: dbt
""",
    "dataproducts/agg_order_dbt/src/raw.py": """\
import os

import psycopg


def build():
    with psycopg.connect(os.environ["WAREHOUSE_URL"], autocommit=True) as db:
        db.execute("CREATE SCHEMA IF NOT EXISTS agg_order_dbt_private")
        db.execute("DROP TABLE IF EXISTS agg_order_dbt_private.raw")
        db.execute("CREATE TABLE agg_order_dbt_private.raw (id integer)")
        db.execute("INSERT INTO agg_order_dbt_private.raw VALUES (1), (2), (3)")
""",
    "dataproducts/agg_order_dbt/models/agg_order_dbt__totals.sql": (
        "select count(*)::integer as n from agg_order_dbt_private.raw\n"
    ),
}


def doc_block(containing: str) -> str:
    """The one fenced Python block of the how-to that contains `containing`; the tests run the page's own code."""
    blocks = re.findall(r"```python\n(.*?)```", DOC.read_text(), re.DOTALL)
    found = [block for block in blocks if containing in block]
    assert len(found) == 1, f"{len(found)} blocks of {DOC.name} contain {containing!r}"
    return found[0]


def write_files(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def generate(root: Path) -> None:
    result = generate_repo(root)
    assert result.report.ok, result.report


@dataclass
class Project:
    dg: Any  # the dagster module
    defs: Any
    instance: Any
    query: Callable[[str], list[tuple[Any, ...]]]

    def run(self, job: str) -> Any:
        """Run a job in process on the instance; a failed run is returned, not raised."""
        return self.defs.resolve_job_def(job).execute_in_process(instance=self.instance, raise_on_error=False)

    def rows(self, statement: str) -> list[tuple[Any, ...]]:
        return self.query(statement)

    def materialized(self, *key: str) -> bool:
        return self.instance.get_latest_materialization_event(self.dg.AssetKey(list(key))) is not None


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def forget_generated_modules() -> None:
    for name in list(sys.modules):
        if name in ("definitions", "generated") or name.startswith(("generated.", "generated_")):
            del sys.modules[name]


@pytest.fixture
def dagster_module() -> Any:
    # Not at module level: the unit tests collect this folder without Dagster installed.
    return pytest.importorskip("dagster")


@pytest.fixture
def project(dagster_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Project]:
    """The repo generated, and the definitions file of the how-to loaded with `DuckDBResource` bound."""
    root = tmp_path / "repo"
    write_files(root, FILES)
    generate(root)
    database = tmp_path / "warehouse.duckdb"
    monkeypatch.setenv("DPB_TEST_DUCKDB", str(database))
    monkeypatch.setenv("WAREHOUSE_DB", str(database))
    monkeypatch.syspath_prepend(str(root))
    (root / "definitions.py").write_text(doc_block("DuckDBResource"))
    importlib.invalidate_caches()

    def query(statement: str) -> list[tuple[Any, ...]]:
        with duckdb.connect(str(database)) as db:
            return db.execute(statement).fetchall()

    module = load_module(root / "definitions.py", "definitions")
    yield Project(dagster_module, module.defs, dagster_module.DagsterInstance.ephemeral(), query)
    forget_generated_modules()


@pytest.fixture
def postgres_roles(postgres_admin: psycopg.Connection) -> Iterator[None]:
    """The roles of the data products; they belong to the server, so drop them after the database is gone."""
    for role in ROLES:
        postgres_admin.execute(
            sql.SQL("DO $$ BEGIN CREATE ROLE {} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$").format(
                sql.Identifier(role)
            )
        )
    yield
    for role in ROLES:
        postgres_admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


@pytest.fixture
def postgres_url(postgres_roles: None, pg_db: psycopg.Connection) -> str:
    """The URL of a fresh database, which the `PostgresResource` of the how-to and the build code connect to."""
    return urlparse(os.environ["DPB_TEST_POSTGRES_URL"])._replace(path=f"/{pg_db.info.dbname}").geturl()


def postgres_query(url: str) -> Callable[[str], list[tuple[Any, ...]]]:
    def query(statement: str) -> list[tuple[Any, ...]]:
        with psycopg.connect(url, autocommit=True) as db:
            return db.execute(statement.encode()).fetchall()

    return query


def postgres_project(dg: Any, root: Path, url: str, monkeypatch: pytest.MonkeyPatch, products: list[str]) -> Project:
    """Load the generated modules of these data products, with the `PostgresResource` block of the how-to bound."""
    monkeypatch.setenv("WAREHOUSE_URL", url)
    namespace: dict[str, Any] = {}
    exec(doc_block("PostgresResource"), namespace)  # the page's own code: the resource class and its binding
    modules = [load_module(root / "generated" / f"{product}.py", f"generated_{product}") for product in products]
    defs = dg.Definitions.merge(*(module.defs for module in modules), namespace["warehouse"])
    return Project(dg, defs, dg.DagsterInstance.ephemeral(), postgres_query(url))


def test_the_merged_definitions_of_two_data_products_are_loadable(project: Project):
    project.dg.Definitions.validate_loadable(project.defs)
    keys = {key.to_user_string() for key in project.defs.resolve_all_asset_keys()}
    assert keys == {
        "sa_jaffle_orders/ingested_orders",
        "sa_jaffle_orders/orders",
        "sa_jaffle_orders",
        "agg_order_turnaround/status_counts",
        "agg_order_turnaround",
    }
    groups = {spec.key.to_user_string(): spec.group_name for spec in project.defs.resolve_all_asset_specs()}
    assert groups["sa_jaffle_orders/orders"] == "sa_jaffle_orders"
    assert groups["agg_order_turnaround"] == "agg_order_turnaround"


def test_a_job_builds_the_tables_and_applies_the_output_port_views(project: Project):
    result = project.run("sa_jaffle_orders")
    assert result.success
    assert project.rows("SELECT order_id, status FROM sa_jaffle_orders_private.orders ORDER BY order_id") == [
        ("o1", "paid"),
        ("o2", "open"),
    ]
    assert project.rows("SELECT order_id FROM sa_jaffle_orders.orders ORDER BY order_id") == [("o1",), ("o2",)]
    assert project.materialized("sa_jaffle_orders")


def test_each_quality_rule_has_its_own_check_result_with_the_violation_count(project: Project):
    result = project.run("sa_jaffle_orders")
    evaluations = {e.check_name: e for e in result.get_asset_check_evaluations()}
    assert sorted(evaluations) == ["accepted_values_status", "not_null_order_id"]
    assert all(e.passed for e in evaluations.values())
    assert evaluations["not_null_order_id"].metadata["violations"].value == 0


def test_a_broken_error_rule_fails_the_run_and_the_output_port_is_not_materialized(
    project: Project, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DPB_TEST_MODE", "null_id")
    result = project.run("sa_jaffle_orders")
    assert not result.success
    evaluations = {e.check_name: e for e in result.get_asset_check_evaluations()}
    assert not evaluations["not_null_order_id"].passed
    assert evaluations["not_null_order_id"].severity == project.dg.AssetCheckSeverity.ERROR
    assert evaluations["not_null_order_id"].metadata["violations"].value == 1
    assert evaluations["accepted_values_status"].passed
    assert project.materialized("sa_jaffle_orders", "orders")
    assert not project.materialized("sa_jaffle_orders")
    schemas = {row[0] for row in project.rows("SELECT schema_name FROM information_schema.schemata")}
    assert "sa_jaffle_orders" not in schemas


def test_a_broken_warning_rule_is_reported_and_the_run_goes_on(project: Project, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DPB_TEST_MODE", "bad_status")
    result = project.run("sa_jaffle_orders")
    assert result.success
    evaluations = {e.check_name: e for e in result.get_asset_check_evaluations()}
    assert not evaluations["accepted_values_status"].passed
    assert evaluations["accepted_values_status"].severity == project.dg.AssetCheckSeverity.WARN
    assert evaluations["accepted_values_status"].metadata["violations"].value == 1
    assert project.materialized("sa_jaffle_orders")


def test_the_job_has_a_running_schedule_with_the_cron_of_the_source_port_in_utc(project: Project):
    schedule = project.defs.resolve_schedule_def("sa_jaffle_orders__schedule")
    assert schedule.cron_schedule == "0 5 * * *"
    assert schedule.execution_timezone == "UTC"
    assert schedule.default_status == project.dg.DefaultScheduleStatus.RUNNING
    assert schedule.job_name == "sa_jaffle_orders"
    with pytest.raises(project.dg.DagsterInvariantViolationError):
        project.defs.resolve_schedule_def("agg_order_turnaround__schedule")


def test_the_reading_data_product_runs_when_the_port_it_reads_is_materialized(project: Project):
    sensor = project.defs.resolve_sensor_def("agg_order_turnaround__on_sa_jaffle_orders")
    assert sensor.default_status == project.dg.DefaultSensorStatus.RUNNING
    assert sensor.job_name == "agg_order_turnaround"

    def requests(cursor: str | None) -> tuple[list[Any], str | None]:
        context = project.dg.build_sensor_context(instance=project.instance, cursor=cursor, definitions=project.defs)
        data = sensor.evaluate_tick(context)
        return list(data.run_requests), data.cursor

    assert requests(None)[0] == []
    assert project.run("sa_jaffle_orders").success
    [request], cursor = requests(None)
    assert request.run_key
    assert requests(cursor)[0] == []

    assert project.run("sa_jaffle_orders").success
    [second], _ = requests(cursor)
    assert second.run_key != request.run_key

    result = project.run("agg_order_turnaround")
    assert result.success
    assert project.rows("SELECT status, n FROM agg_order_turnaround_private.status_counts ORDER BY status") == [
        ("open", 1),
        ("paid", 1),
    ]


def test_the_postgres_resource_of_the_how_to_runs_the_audits_and_applies_the_views(
    dagster_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, postgres_url: str
):
    root = tmp_path / "repo"
    write_files(root, {**FILES, **POSTGRES_SOURCES})
    generate(root)
    products = ["sa_jaffle_orders", "agg_order_turnaround"]
    project = postgres_project(dagster_module, root, postgres_url, monkeypatch, products)
    try:
        dagster_module.Definitions.validate_loadable(project.defs)
        result = project.run("sa_jaffle_orders")
        assert result.success
        evaluations = {e.check_name: e for e in result.get_asset_check_evaluations()}
        assert sorted(evaluations) == ["accepted_values_status", "not_null_order_id"]
        assert all(e.passed for e in evaluations.values())
        assert project.rows("SELECT order_id FROM sa_jaffle_orders.orders ORDER BY order_id") == [("o1",), ("o2",)]
        assert project.materialized("sa_jaffle_orders")
    finally:
        forget_generated_modules()


def test_a_dbt_table_runs_dbt_build_once_after_the_python_table_and_before_the_output_port(
    dagster_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, postgres_url: str
):
    if shutil.which("dbt") is None:
        pytest.fail("dbt is not installed (dependency group `dbt`); run scripts/integration-tests")
    parsed = urlparse(postgres_url)
    profiles = tmp_path / "profiles"
    write_files(
        tmp_path,
        {
            "profiles/profiles.yml": "dpb_dagster:\n  target: dev\n  outputs:\n    dev:\n"
            f"      {{type: postgres, host: '{parsed.hostname}', port: {parsed.port or 5432}, "
            f"user: '{parsed.username}', password: '{parsed.password}', dbname: '{parsed.path.lstrip('/')}', "
            f"schema: dpb_test_{uuid.uuid4().hex[:8]}, threads: 1}}\n",
        },
    )
    root = tmp_path / "repo"
    write_files(root, {**DBT_FILES, "macros/generate_schema_name.sql": MACRO.read_text()})
    (root / "datapatchbay.yaml").write_text(DBT_FILES["datapatchbay.yaml"] + f"dbt:\n  profiles_dir: {profiles}\n")
    generate(root)
    project = postgres_project(dagster_module, root, postgres_url, monkeypatch, ["agg_order_dbt"])
    try:
        dagster_module.Definitions.validate_loadable(project.defs)
        keys = {key.to_user_string() for key in project.defs.resolve_all_asset_keys()}
        assert keys == {"agg_order_dbt/raw", "agg_order_dbt/totals", "agg_order_dbt"}
        result = project.run("agg_order_dbt")
        assert result.success, [str(e.event_specific_data) for e in result.get_step_failure_events()]
        dbt_steps = [e for e in result.all_events if e.event_type_value == "STEP_START" and "build_dbt" in e.step_key]
        assert len(dbt_steps) == 1
        built = [e.asset_key.to_user_string() for e in result.get_asset_materialization_events()]
        assert built == ["agg_order_dbt/raw", "agg_order_dbt/totals", "agg_order_dbt"]
        assert project.rows("SELECT n FROM agg_order_dbt_private.totals") == [(3,)]  # dbt read the Python table
        assert project.rows("SELECT n FROM agg_order_dbt.totals") == [(3,)]
        assert project.materialized("agg_order_dbt")
    finally:
        forget_generated_modules()
