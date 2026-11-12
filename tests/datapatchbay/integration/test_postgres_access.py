"""The SQL that makes an output port real in Postgres, applied to a real Postgres (ADR-0002, ADR-0007).

Integration tests: they query as a reader and a PII reader, so they need roles and grants that DuckDB does not have
(ADR-0020).
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest
from access_support import ORDERS, ORDERS_FILE, PORT, PORT_FILE, apply_sql
from psycopg import sql

ROLES = ("grp-lab-reporting", "grp-lab-doctors", "grp-outsider", "dp_agg_lab_turnaround", "grp-lab-former")


@pytest.fixture
def repo(lab_repo: Path) -> Path:
    (lab_repo / PORT).write_text(PORT_FILE)
    (lab_repo / ORDERS).write_text(ORDERS_FILE)
    return lab_repo


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


def test_a_reader_sees_null_in_a_pii_column_and_a_pii_reader_sees_the_value(
    repo: Path, warehouse: psycopg.Connection, query_as: QueryAs
):
    run(warehouse, apply_sql(repo))
    assert query_as("grp-lab-reporting", VIEW) == MASKED
    assert query_as("grp-lab-doctors", VIEW) == UNMASKED


def test_a_product_reader_reads_through_the_role_of_its_data_product(
    repo: Path, warehouse: psycopg.Connection, query_as: QueryAs
):
    run(warehouse, apply_sql(repo))
    assert query_as("dp_agg_lab_turnaround", VIEW) == MASKED


@pytest.mark.parametrize("role", ["grp-lab-reporting", "grp-lab-doctors", "dp_agg_lab_turnaround"])
def test_nobody_is_granted_access_to_the_private_schema(
    repo: Path, warehouse: psycopg.Connection, query_as: QueryAs, role: str
):
    run(warehouse, apply_sql(repo))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        query_as(role, PRIVATE)


def test_someone_who_is_not_a_reader_cannot_read_the_view(repo: Path, warehouse: psycopg.Connection, query_as: QueryAs):
    run(warehouse, apply_sql(repo))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        query_as("grp-outsider", VIEW)


def test_applying_again_gives_the_same_result(repo: Path, warehouse: psycopg.Connection, query_as: QueryAs):
    statements = apply_sql(repo)
    run(warehouse, statements)
    run(warehouse, statements)
    assert query_as("grp-lab-reporting", VIEW) == MASKED
    assert query_as("grp-lab-doctors", VIEW) == UNMASKED


def test_a_removed_reader_loses_access_on_the_next_apply(repo: Path, warehouse: psycopg.Connection, query_as: QueryAs):
    (repo / PORT).write_text(PORT_FILE.replace("grp-lab-reporting", "grp-lab-former"))
    run(warehouse, apply_sql(repo))
    assert query_as("grp-lab-former", VIEW) == MASKED
    (repo / PORT).write_text(PORT_FILE)
    run(warehouse, apply_sql(repo))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        query_as("grp-lab-former", VIEW)
    assert query_as("grp-lab-reporting", VIEW) == MASKED


def test_a_removed_pii_reader_loses_access_on_the_next_apply(
    repo: Path, warehouse: psycopg.Connection, query_as: QueryAs
):
    run(warehouse, apply_sql(repo))
    (repo / PORT).write_text(PORT_FILE.replace("pii_readers: [grp-lab-doctors]", "pii_readers: []"))
    run(warehouse, apply_sql(repo))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        query_as("grp-lab-doctors", VIEW)


def test_a_column_removed_from_the_table_file_applies_cleanly(
    repo: Path, warehouse: psycopg.Connection, query_as: QueryAs
):
    run(warehouse, apply_sql(repo))
    (repo / ORDERS).write_text(ORDERS_FILE.replace("  - name: status\n    type: text\n", ""))
    run(warehouse, apply_sql(repo))
    assert query_as("grp-lab-doctors", VIEW) == [("o1", "p1"), ("o2", "p2")]


def test_a_failing_apply_changes_nothing(repo: Path, warehouse: psycopg.Connection, query_as: QueryAs):
    run(warehouse, apply_sql(repo))
    (repo / PORT).write_text(PORT_FILE.replace("grp-lab-reporting", "grp-does-not-exist"))
    with pytest.raises(psycopg.errors.UndefinedObject):
        run(warehouse, apply_sql(repo))
    assert query_as("grp-lab-reporting", VIEW) == MASKED
