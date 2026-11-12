"""The views of the DuckDB warehouse, applied to an in-process DuckDB and read back (ADR-0002, ADR-0020, ADR-0021)."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import duckdb
import pytest
from audit_support import SCHEMA
from plan_helpers import plan_all

from datapatchbay.generate import generate_repo
from datapatchbay.integrations.duckdb.warehouse import DuckDbWarehouse
from datapatchbay.loading import load_repo
from datapatchbay.plugins import DataProductPlan

PORT = "dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/port.yaml"
ORDERS = "dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/orders.yaml"
PORT_FILE = """\
schema_version: 1
kind: schema
freshness: 24h
access:
  readers:
    - grp-shop-reporting
    - product: agg_order_turnaround
    - product: agg_weekly_orders
  pii_readers: [grp-shop-support]
"""
ORDERS_HEAD = "schema_version: 1\nname: orders\ncolumns:\n"
ORDERS_COLUMNS = """\
  - name: order_id
    type: text
  - name: customer_id
    type: text
    pii: true
  - name: status
    type: text
"""
ORDERS_TAIL = "build:\n  entrypoint: src/orders.py:build\n  needs: [ingested_orders]\n"


@pytest.fixture
def db() -> Iterator[duckdb.DuckDBPyConnection]:
    with duckdb.connect(":memory:") as connection:
        connection.execute(f"CREATE SCHEMA {SCHEMA}")
        connection.execute(f"CREATE TABLE {SCHEMA}.orders (order_id text, customer_id text, status text)")
        connection.execute(f"INSERT INTO {SCHEMA}.orders VALUES ('o1', 'c1', 'new'), ('o2', 'c2', 'done')")
        yield connection


@pytest.fixture
def repo(jaffle_repo: Path) -> Path:
    (jaffle_repo / PORT).write_text(PORT_FILE)
    write_orders(jaffle_repo, ORDERS_COLUMNS)
    return jaffle_repo


def write_orders(root: Path, columns: str) -> None:
    (root / ORDERS).write_text(ORDERS_HEAD + columns + ORDERS_TAIL)


def plan_of(root: Path) -> DataProductPlan:
    loaded, problems = load_repo(root)
    assert problems == []
    return next(p for p in plan_all(loaded, root) if p.folder == "sa_jaffle_orders")


def apply_sql(root: Path) -> str:
    (task,) = DuckDbWarehouse().apply_tasks(plan_of(root))
    assert task.task_id == "apply_access"
    return task.sql


def test_the_views_of_a_port_read_the_private_table_with_the_columns_of_the_table_file(
    repo: Path, db: duckdb.DuckDBPyConnection
):
    db.execute(apply_sql(repo))
    result = db.execute("SELECT * FROM sa_jaffle_orders.orders ORDER BY order_id")
    assert [d[0] for d in result.description] == ["order_id", "customer_id", "status"]
    assert [(r[0], r[2]) for r in result.fetchall()] == [("o1", "new"), ("o2", "done")]


def test_a_pii_column_shows_null_to_everyone_and_keeps_its_type(repo: Path, db: duckdb.DuckDBPyConnection):
    db.execute(apply_sql(repo))
    assert db.execute("SELECT customer_id FROM sa_jaffle_orders.orders").fetchall() == [(None,), (None,)]
    assert db.execute("SELECT typeof(customer_id) FROM sa_jaffle_orders.orders LIMIT 1").fetchone() == ("VARCHAR",)


def test_readers_and_pii_readers_create_no_grants_and_no_roles(repo: Path):
    text = apply_sql(repo)
    for word in ("GRANT", "REVOKE", "grp-shop", "dp_agg_order_turnaround"):
        assert word not in text


def test_applying_again_gives_the_same_result(repo: Path, db: duckdb.DuckDBPyConnection):
    db.execute(apply_sql(repo))
    first = db.execute("SELECT * FROM sa_jaffle_orders.orders ORDER BY order_id").fetchall()
    db.execute(apply_sql(repo))
    assert db.execute("SELECT * FROM sa_jaffle_orders.orders ORDER BY order_id").fetchall() == first


def test_a_column_removed_from_the_table_file_is_gone_from_the_view_after_the_next_apply(
    repo: Path, db: duckdb.DuckDBPyConnection
):
    db.execute(apply_sql(repo))
    write_orders(repo, ORDERS_COLUMNS.replace("  - name: status\n    type: text\n", ""))
    db.execute(apply_sql(repo))
    result = db.execute("SELECT * FROM sa_jaffle_orders.orders")
    assert [d[0] for d in result.description] == ["order_id", "customer_id"]


def test_a_view_of_a_table_that_left_the_port_is_gone_after_the_next_apply(repo: Path, db: duckdb.DuckDBPyConnection):
    db.execute(f"CREATE TABLE {SCHEMA}.leftover (a integer)")
    db.execute("CREATE SCHEMA sa_jaffle_orders")
    db.execute(f"CREATE VIEW sa_jaffle_orders.leftover AS SELECT * FROM {SCHEMA}.leftover")
    db.execute(apply_sql(repo))
    rows = db.execute("SELECT view_name FROM duckdb_views() WHERE schema_name = 'sa_jaffle_orders'").fetchall()
    assert {row[0] for row in rows} == {"orders"}


def test_a_name_with_a_quote_is_escaped(repo: Path):
    write_orders(repo, "  - name: 'we\"ird'\n    type: text\n")
    assert '"we""ird"' in apply_sql(repo)


def test_a_data_product_without_output_ports_applies_nothing(repo: Path):
    assert DuckDbWarehouse().apply_tasks(replace(plan_of(repo), outputs=())) == ()


def test_generate_ends_the_dag_with_the_apply_task_before_publishing_the_outputs(repo: Path):
    (repo / "datapatchbay.yaml").write_text("schema_version: 1\nwarehouse: duckdb\n")
    report = generate_repo(repo).report
    assert report.ok, report
    dag = (repo / "generated/sa_jaffle_orders.py").read_text()
    assert "apply_access" in dag
    assert dag.index("apply_access") < dag.rindex("publish_outputs")


def test_a_failing_apply_leaves_the_previous_views(repo: Path, db: duckdb.DuckDBPyConnection):
    db.execute(apply_sql(repo))
    before = db.execute("SELECT * FROM sa_jaffle_orders.orders ORDER BY order_id").fetchall()
    db.execute(f"ALTER TABLE {SCHEMA}.orders DROP COLUMN status")
    with pytest.raises(duckdb.Error):
        db.execute(apply_sql(repo))
    db.execute("ROLLBACK")
    db.execute(f"ALTER TABLE {SCHEMA}.orders ADD COLUMN status text")
    rows = db.execute("SELECT order_id, customer_id, status FROM sa_jaffle_orders.orders ORDER BY order_id").fetchall()
    assert [(r[0], r[1]) for r in rows] == [(r[0], r[1]) for r in before]


def test_the_apply_is_one_transaction(repo: Path):
    lines = apply_sql(repo).splitlines()
    assert lines[0] == "BEGIN TRANSACTION;"
    assert lines[-1] == "COMMIT;"
