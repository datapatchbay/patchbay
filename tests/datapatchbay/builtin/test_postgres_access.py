"""The SQL that makes an output port real in Postgres: views, masking and grants (ADR-0002, ADR-0007).

Tests marked `postgres` apply the SQL to a real Postgres and query as a reader and a PII reader. They need
`DPB_TEST_POSTGRES_URL`, a URL of a Postgres server where the user may create databases and roles, and are skipped
without it.
"""

import re
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from datapatchbay.builtin.postgres import PostgresWarehouse
from datapatchbay.builtin.postgres_access import _dollar_tag
from datapatchbay.errors import DatapatchbayError
from datapatchbay.loading import load_repo
from datapatchbay.planning import plan_dataproducts
from datapatchbay.plugins import DataProductPlan
from datapatchbay.settings import load_settings

PORT = "dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/port.yaml"
ORDERS = "dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/orders.yaml"

PORT_FILE = """\
schema_version: 1
kind: schema
freshness: 24h
access:
  readers:
    - grp-lab-reporting
    - product: agg_lab_turnaround
  pii_readers: [grp-lab-doctors]
"""
ORDERS_FILE = """\
schema_version: 1
name: orders
columns:
  - name: order_id
    type: text
  - name: patient_id
    type: text
    pii: true
  - name: status
    type: text
build:
  entrypoint: src/orders.py:build
  needs: [ingested_orders]
"""
SNAPSHOT = (Path(__file__).parent / "postgres_access_snapshot.sql").read_text()
ROLES = ("grp-lab-reporting", "grp-lab-doctors", "grp-outsider", "dp_agg_lab_turnaround", "grp-lab-former")


@pytest.fixture
def repo(lab_repo: Path) -> Path:
    (lab_repo / PORT).write_text(PORT_FILE)
    (lab_repo / ORDERS).write_text(ORDERS_FILE)
    return lab_repo


def plan_of(root: Path) -> DataProductPlan:
    loaded, problems = load_repo(root)
    assert problems == []
    return next(p for p in plan_dataproducts(loaded, load_settings(root)) if p.folder == "sa_ilab_orders")


def apply_sql(root: Path) -> str:
    (task,) = PostgresWarehouse().apply_tasks(plan_of(root))
    return task.sql


def test_the_apply_is_one_task_with_a_stable_id_and_the_same_sql_for_the_same_input(repo: Path):
    (task,) = PostgresWarehouse().apply_tasks(plan_of(repo))
    assert task.task_id == "apply_access"
    assert apply_sql(repo) == apply_sql(repo)


def test_the_sql_is_the_same_text_as_before_the_view_statement_was_shared_with_duckdb(repo: Path):
    assert apply_sql(repo) == SNAPSHOT


def test_a_data_product_without_output_ports_applies_nothing(repo: Path):
    assert PostgresWarehouse().apply_tasks(replace(plan_of(repo), outputs=())) == ()


def test_the_sql_names_roles_through_the_role_template_and_never_grants_on_the_private_schema(repo: Path):
    text = apply_sql(repo)
    assert '"dp_agg_lab_turnaround"' in text
    assert not re.search(r"GRANT[^;]*sa_ilab_orders_private", text)


def test_an_identifier_with_a_quote_is_escaped(repo: Path):
    (repo / PORT).write_text(PORT_FILE.replace("grp-lab-reporting", 'we"ird'))
    assert '"we""ird"' in apply_sql(repo)


def test_a_dollar_quote_tag_never_occurs_in_the_text_it_wraps():
    assert _dollar_tag("plain") == "$body$"
    assert _dollar_tag("a$body$b") not in "a$body$b"


def test_a_product_reader_that_is_not_a_data_product_is_an_error(repo: Path):
    (repo / PORT).write_text(PORT_FILE.replace("agg_lab_turnaround", "nope"))
    with pytest.raises(DatapatchbayError, match="nope"):
        apply_sql(repo)


# ---- against a real Postgres ---------------------------------------------------------------------------------------


@pytest.fixture
def roles(postgres_admin: psycopg.Connection) -> Iterator[None]:
    """Drop the roles after the database that uses them is gone: roles belong to the whole server."""
    yield
    for role in ROLES:
        postgres_admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


@pytest.fixture
def warehouse(roles: None, pg_db: psycopg.Connection) -> psycopg.Connection:
    """A fresh database with a private schema holding the built table, and the roles."""
    connection = pg_db
    for role in ROLES:
        connection.execute(
            sql.SQL("DO $$ BEGIN CREATE ROLE {} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$").format(
                sql.Identifier(role)
            )
        )
    connection.execute("CREATE SCHEMA sa_ilab_orders_private")
    connection.execute("CREATE TABLE sa_ilab_orders_private.orders (order_id text, patient_id text, status text)")
    connection.execute("INSERT INTO sa_ilab_orders_private.orders VALUES ('o1', 'p1', 'open'), ('o2', 'p2', 'closed')")
    return connection


type QueryAs = Callable[[str, str], list[tuple[object, ...]]]


def run(connection: psycopg.Connection, statements: str) -> None:
    connection.execute(statements.encode())


@pytest.fixture
def query_as(warehouse: psycopg.Connection) -> QueryAs:
    def query(role: str, statement: str) -> list[tuple[object, ...]]:
        warehouse.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
        try:
            return warehouse.execute(statement.encode()).fetchall()
        finally:
            warehouse.execute("RESET ROLE")

    return query


VIEW = "SELECT * FROM sa_ilab_orders.orders ORDER BY order_id"
PRIVATE = "SELECT * FROM sa_ilab_orders_private.orders"
MASKED = [("o1", None, "open"), ("o2", None, "closed")]
UNMASKED = [("o1", "p1", "open"), ("o2", "p2", "closed")]


@pytest.mark.postgres
def test_a_reader_sees_null_in_a_pii_column_and_a_pii_reader_sees_the_value(
    repo: Path, warehouse: psycopg.Connection, query_as: QueryAs
):
    run(warehouse, apply_sql(repo))
    assert query_as("grp-lab-reporting", VIEW) == MASKED
    assert query_as("grp-lab-doctors", VIEW) == UNMASKED


@pytest.mark.postgres
def test_a_product_reader_reads_through_the_role_of_its_data_product(
    repo: Path, warehouse: psycopg.Connection, query_as: QueryAs
):
    run(warehouse, apply_sql(repo))
    assert query_as("dp_agg_lab_turnaround", VIEW) == MASKED


@pytest.mark.postgres
@pytest.mark.parametrize("role", ["grp-lab-reporting", "grp-lab-doctors", "dp_agg_lab_turnaround"])
def test_nobody_is_granted_access_to_the_private_schema(
    repo: Path, warehouse: psycopg.Connection, query_as: QueryAs, role: str
):
    run(warehouse, apply_sql(repo))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        query_as(role, PRIVATE)


@pytest.mark.postgres
def test_someone_who_is_not_a_reader_cannot_read_the_view(repo: Path, warehouse: psycopg.Connection, query_as: QueryAs):
    run(warehouse, apply_sql(repo))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        query_as("grp-outsider", VIEW)


@pytest.mark.postgres
def test_applying_again_gives_the_same_result(repo: Path, warehouse: psycopg.Connection, query_as: QueryAs):
    statements = apply_sql(repo)
    run(warehouse, statements)
    run(warehouse, statements)
    assert query_as("grp-lab-reporting", VIEW) == MASKED
    assert query_as("grp-lab-doctors", VIEW) == UNMASKED


@pytest.mark.postgres
def test_a_removed_reader_loses_access_on_the_next_apply(repo: Path, warehouse: psycopg.Connection, query_as: QueryAs):
    (repo / PORT).write_text(PORT_FILE.replace("grp-lab-reporting", "grp-lab-former"))
    run(warehouse, apply_sql(repo))
    assert query_as("grp-lab-former", VIEW) == MASKED
    (repo / PORT).write_text(PORT_FILE)
    run(warehouse, apply_sql(repo))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        query_as("grp-lab-former", VIEW)
    assert query_as("grp-lab-reporting", VIEW) == MASKED


@pytest.mark.postgres
def test_a_removed_pii_reader_loses_access_on_the_next_apply(
    repo: Path, warehouse: psycopg.Connection, query_as: QueryAs
):
    run(warehouse, apply_sql(repo))
    (repo / PORT).write_text(PORT_FILE.replace("pii_readers: [grp-lab-doctors]", "pii_readers: []"))
    run(warehouse, apply_sql(repo))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        query_as("grp-lab-doctors", VIEW)


@pytest.mark.postgres
def test_a_column_removed_from_the_table_file_applies_cleanly(
    repo: Path, warehouse: psycopg.Connection, query_as: QueryAs
):
    run(warehouse, apply_sql(repo))
    (repo / ORDERS).write_text(ORDERS_FILE.replace("  - name: status\n    type: text\n", ""))
    run(warehouse, apply_sql(repo))
    assert query_as("grp-lab-doctors", VIEW) == [("o1", "p1"), ("o2", "p2")]


@pytest.mark.postgres
def test_a_failing_apply_changes_nothing(repo: Path, warehouse: psycopg.Connection, query_as: QueryAs):
    run(warehouse, apply_sql(repo))
    (repo / PORT).write_text(PORT_FILE.replace("grp-lab-reporting", "grp-does-not-exist"))
    with pytest.raises(psycopg.errors.UndefinedObject):
        run(warehouse, apply_sql(repo))
    assert query_as("grp-lab-reporting", VIEW) == MASKED
