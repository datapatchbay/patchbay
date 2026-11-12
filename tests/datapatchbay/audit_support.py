"""Helpers for the audit tests: plan a table with given quality rules and run its audit like the generated DAG does."""

import logging
import textwrap
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psycopg

from datapatchbay.builtin.airflow_audit import AUDIT_HELPER, check_rows
from datapatchbay.builtin.postgres import PostgresWarehouse
from datapatchbay.loading import load_repo
from datapatchbay.planning import plan_dataproducts
from datapatchbay.plugins import AuditTask, Warehouse
from datapatchbay.settings import load_settings

SCHEMA = "sa_ilab_orders_private"
"""Where the output table `orders` of the fixture data product is built."""

TABLE_HEAD = "schema_version: 1\nname: orders\nbuild:\n  entrypoint: src/orders.py:build\n"


def audit_of(
    root: Path, table_yaml: str, *, settings: str = "", warehouse: Warehouse | None = None
) -> AuditTask | None:
    """Replace `orders.yaml` in a copy of the fixture repo, plan it and return the warehouse's audit of `orders`.

    The warehouse is Postgres unless another one is given.
    """
    (root / "dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/orders.yaml").write_text(
        TABLE_HEAD + textwrap.dedent(table_yaml)
    )
    if settings:
        (root / "datapatchbay.yaml").write_text("schema_version: 1\n" + settings)
    repo, problems = load_repo(root)
    assert problems == []
    plan = next(p for p in plan_dataproducts(repo, load_settings(root)) if p.folder == "sa_ilab_orders")
    table = next(t for t in plan.tables if t.name == "orders")
    tasks = (warehouse or PostgresWarehouse()).audit_tasks(table)
    assert len(tasks) <= 1
    if not tasks:
        return None
    assert isinstance(tasks[0], AuditTask)
    return tasks[0]


def execute(connection: psycopg.Connection, statement: str) -> psycopg.Cursor:
    """Run a statement that the test built as text; psycopg only types literal strings."""
    return connection.execute(statement)  # ty: ignore[no-matching-overload] - the SQL is built from test constants


def run_audit_with(count: Callable[[str], int], task: AuditTask | None) -> None:
    """Run the audit with the code that is generated into the DAG file; `count` runs one query for its number."""
    assert task is not None
    namespace: dict[str, Any] = {"logging": logging}
    exec(AUDIT_HELPER, namespace)
    namespace["_run_audit"](check_rows(task), count)


def run_audit(connection: psycopg.Connection, task: AuditTask | None) -> None:
    """Run the audit with the code that is generated into the DAG file, counting violations on `connection`."""

    def count(sql: str) -> int:
        row = execute(connection, sql).fetchone()
        assert row is not None
        return row[0]

    run_audit_with(count, task)


def load_orders(connection: psycopg.Connection, rows: str, columns: str = "order_id text, status text, qty integer"):
    """Create the private schema with an `orders` table holding `rows` (a SQL VALUES list)."""
    execute(connection, f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    execute(connection, f"CREATE SCHEMA {SCHEMA}")
    execute(connection, f"CREATE TABLE {SCHEMA}.orders ({columns})")
    if rows:
        execute(connection, f"INSERT INTO {SCHEMA}.orders VALUES {rows}")


def columns_yaml(order_id_rules: str = "", status_rules: str = "", qty_rules: str = "") -> str:
    """The columns `order_id`, `status` and `qty`; each `*_rules` is the YAML list items for that column."""

    def column(name: str, type_: str, rules: str) -> str:
        block = f"    rules:\n{textwrap.indent(rules, '      ')}" if rules else ""
        return f"  - name: {name}\n    type: {type_}\n{block}"

    return (
        "columns:\n"
        + column("order_id", "text", order_id_rules)
        + column("status", "text", status_rules)
        + column("qty", "integer", qty_rules)
    )
