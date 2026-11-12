"""The audit SQL of the DuckDB warehouse, run in an in-process DuckDB through the audit code of the DAG file."""

import logging
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest
from audit_support import SCHEMA, columns_yaml, run_audit_with
from audit_support import audit_of as _audit_of

from datapatchbay.integrations.duckdb.warehouse import DuckDbWarehouse
from datapatchbay.plugins import AuditTask


@pytest.fixture
def db() -> Iterator[duckdb.DuckDBPyConnection]:
    """A DuckDB inside the test process, in memory, so no file is written."""
    with duckdb.connect(":memory:") as connection:
        yield connection


@pytest.fixture
def shop(jaffle_repo: Path) -> Path:
    return jaffle_repo


def audit_of(root: Path, table_yaml: str) -> AuditTask | None:
    return _audit_of(root, table_yaml, warehouse=DuckDbWarehouse())


def run_audit(connection: duckdb.DuckDBPyConnection, task: AuditTask | None) -> None:
    """Run the audit with the code that is generated into the DAG file, counting violations in DuckDB."""

    def count(sql: str) -> int:
        row = connection.execute(sql).fetchone()
        assert row is not None
        return row[0]

    run_audit_with(count, task)


def load_orders(
    connection: duckdb.DuckDBPyConnection, rows: str, columns: str = "order_id text, status text, qty integer"
) -> None:
    """Create the private schema with an `orders` table holding `rows` (a SQL VALUES list)."""
    connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    connection.execute(f"CREATE SCHEMA {SCHEMA}")
    connection.execute(f"CREATE TABLE {SCHEMA}.orders ({columns})")
    if rows:
        connection.execute(f"INSERT INTO {SCHEMA}.orders VALUES {rows}")


@pytest.mark.parametrize(
    ("rule", "rows", "message"),
    [
        (
            "not_null",
            "('a','x',1),(NULL,'x',1),(NULL,'x',1)",
            "quality rule 'not_null' is broken on table 'orders', column 'order_id': 2",
        ),
        (
            "unique",
            "('a','x',1),('a','x',1),('b','x',1),(NULL,'x',1),(NULL,'x',1)",
            "quality rule 'unique' is broken on table 'orders', column 'order_id': 1",
        ),
    ],
)
def test_a_broken_column_rule_with_severity_error_fails_naming_rule_table_and_column(
    db: duckdb.DuckDBPyConnection, shop: Path, rule: str, rows: str, message: str
):
    load_orders(db, rows)
    task = audit_of(shop, columns_yaml(order_id_rules=f"- {rule}\n"))
    with pytest.raises(RuntimeError, match=message):
        run_audit(db, task)


@pytest.mark.parametrize("rule", ["not_null", "unique"])
def test_column_rules_pass_on_clean_data(db: duckdb.DuckDBPyConnection, shop: Path, rule: str):
    load_orders(db, "('a','x',1),('b','x',1)")
    run_audit(db, audit_of(shop, columns_yaml(order_id_rules=f"- {rule}\n")))


def test_accepted_values_fails_on_a_value_outside_the_list_and_ignores_nulls(db: duckdb.DuckDBPyConnection, shop: Path):
    table = columns_yaml(status_rules='- rule: accepted_values\n  values: [open, "it\'s closed"]\n')
    load_orders(db, "('a','open',1),('b',NULL,1),('c','it''s closed',1)")
    run_audit(db, audit_of(shop, table))
    load_orders(db, "('a','open',1),('b','lost',1)")
    with pytest.raises(RuntimeError, match="'accepted_values' is broken on table 'orders', column 'status': 1"):
        run_audit(db, audit_of(shop, table))


def test_accepted_values_compares_numbers_and_booleans_by_their_type(db: duckdb.DuckDBPyConnection, shop: Path):
    table = columns_yaml(qty_rules="- rule: accepted_values\n  values: [1, 2.5]\n") + (
        "  - name: flag\n    type: boolean\n    rules:\n      - rule: accepted_values\n        values: [true]\n"
    )
    columns = "order_id text, status text, qty numeric, flag boolean"
    load_orders(db, "('a','x',1,true),('b','x',2.5,NULL)", columns)
    run_audit(db, audit_of(shop, table))
    load_orders(db, "('a','x',3,true),('b','x',1,false)", columns)
    with pytest.raises(RuntimeError) as raised:
        run_audit(db, audit_of(shop, table))
    assert "column 'qty': 1" in str(raised.value)
    assert "column 'flag': 1" in str(raised.value)


def test_primary_key_fails_on_nulls_and_on_repeated_combinations(db: duckdb.DuckDBPyConnection, shop: Path):
    table = columns_yaml() + "rules:\n  - rule: primary_key\n    columns: [order_id, status]\n"
    load_orders(db, "('a','x',1),('a','y',1),('b',NULL,1)")
    with pytest.raises(RuntimeError, match=r"'primary_key' is broken on table 'orders', column 'order_id, status': 1"):
        run_audit(db, audit_of(shop, table))
    load_orders(db, "('a','x',1),('a','x',2)")
    with pytest.raises(RuntimeError, match="'primary_key' is broken"):
        run_audit(db, audit_of(shop, table))
    load_orders(db, "('a','x',1),('a','y',2)")
    run_audit(db, audit_of(shop, table))


@pytest.mark.parametrize(
    ("bounds", "count", "broken"),
    [
        ("min: 2", 1, True),
        ("min: 2", 2, False),
        ("max: 2", 3, True),
        ("max: 2", 2, False),
        ("min: 1, max: 2", 0, True),
        ("min: 1, max: 2", 2, False),
    ],
)
def test_row_count_checks_the_bounds(db: duckdb.DuckDBPyConnection, shop: Path, bounds: str, count: int, broken: bool):
    table = columns_yaml() + f"rules:\n  - {{rule: row_count, {bounds}}}\n"
    load_orders(db, ",".join("('a','x',1)" for _ in range(count)))
    task = audit_of(shop, table)
    if broken:
        with pytest.raises(RuntimeError, match="'row_count' is broken on table 'orders'"):
            run_audit(db, task)
    else:
        run_audit(db, task)


def test_a_custom_sql_rule_is_broken_when_its_query_returns_rows(db: duckdb.DuckDBPyConnection, shop: Path):
    table = (
        columns_yaml()
        + f"rules:\n  - rule: sql\n    sql: |\n      SELECT order_id FROM {SCHEMA}.orders WHERE qty < 0;\n"
    )
    load_orders(db, "('a','x',1)")
    run_audit(db, audit_of(shop, table))
    load_orders(db, "('a','x',-1),('b','x',-5)")
    with pytest.raises(RuntimeError, match="quality rule 'sql' is broken on table 'orders': 2"):
        run_audit(db, audit_of(shop, table))


def test_a_broken_warning_is_logged_and_the_audit_succeeds(
    db: duckdb.DuckDBPyConnection, shop: Path, caplog: pytest.LogCaptureFixture
):
    table = columns_yaml(order_id_rules="- {rule: not_null, severity: warning}\n")
    load_orders(db, "(NULL,'x',1)")
    with caplog.at_level(logging.WARNING):
        run_audit(db, audit_of(shop, table))
    assert "quality rule 'not_null' is broken on table 'orders', column 'order_id': 1" in caplog.text


def test_all_broken_errors_are_reported_together_and_warnings_do_not_fail(
    db: duckdb.DuckDBPyConnection, shop: Path, caplog: pytest.LogCaptureFixture
):
    table = columns_yaml(
        order_id_rules="- not_null\n",
        status_rules="- {rule: accepted_values, values: [open], severity: warning}\n",
        qty_rules="- not_null\n",
    )
    load_orders(db, "(NULL,'lost',NULL)")
    with caplog.at_level(logging.WARNING), pytest.raises(RuntimeError) as raised:
        run_audit(db, audit_of(shop, table))
    assert "column 'order_id'" in str(raised.value)
    assert "column 'qty'" in str(raised.value)
    assert "column 'status'" not in str(raised.value)
    assert "column 'status'" in caplog.text


def test_a_rule_with_severity_none_is_not_run_even_when_broken(
    db: duckdb.DuckDBPyConnection, shop: Path, caplog: pytest.LogCaptureFixture
):
    table = columns_yaml(order_id_rules="- not_null\n", qty_rules="- {rule: not_null, severity: none}\n")
    load_orders(db, "('a','x',NULL)")
    with caplog.at_level(logging.WARNING):
        run_audit(db, audit_of(shop, table))
    assert "column 'qty'" not in caplog.text
