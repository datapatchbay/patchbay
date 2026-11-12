"""The audit SQL of the Postgres warehouse, run against a real Postgres through the code generated into the DAG file.

Integration tests (ADR-0020). What they check about a rule is also checked on DuckDB by the unit tests."""

import logging
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from audit_support import SCHEMA, audit_of, columns_yaml, load_orders, run_audit


@pytest.fixture
def lab(pg_db: psycopg.Connection, lab_repo: Path) -> Iterator[Path]:
    yield lab_repo
    pg_db.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")


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
    pg_db: psycopg.Connection, lab: Path, rule: str, rows: str, message: str
):
    load_orders(pg_db, rows)
    task = audit_of(lab, columns_yaml(order_id_rules=f"- {rule}\n"))
    with pytest.raises(RuntimeError, match=message):
        run_audit(pg_db, task)


@pytest.mark.parametrize("rule", ["not_null", "unique"])
def test_column_rules_pass_on_clean_data(pg_db: psycopg.Connection, lab: Path, rule: str):
    load_orders(pg_db, "('a','x',1),('b','x',1)")
    run_audit(pg_db, audit_of(lab, columns_yaml(order_id_rules=f"- {rule}\n")))


def test_accepted_values_fails_on_a_value_outside_the_list_and_ignores_nulls(pg_db: psycopg.Connection, lab: Path):
    table = columns_yaml(status_rules='- rule: accepted_values\n  values: [open, "it\'s closed"]\n')
    load_orders(pg_db, "('a','open',1),('b',NULL,1),('c','it''s closed',1)")
    run_audit(pg_db, audit_of(lab, table))
    load_orders(pg_db, "('a','open',1),('b','lost',1)")
    with pytest.raises(RuntimeError, match="'accepted_values' is broken on table 'orders', column 'status': 1"):
        run_audit(pg_db, audit_of(lab, table))


def test_accepted_values_compares_numbers_and_booleans_by_their_type(pg_db: psycopg.Connection, lab: Path):
    table = columns_yaml(qty_rules="- rule: accepted_values\n  values: [1, 2.5]\n") + (
        "  - name: flag\n    type: boolean\n    rules:\n      - rule: accepted_values\n        values: [true]\n"
    )
    columns = "order_id text, status text, qty numeric, flag boolean"
    load_orders(pg_db, "('a','x',1,true),('b','x',2.5,NULL)", columns)
    run_audit(pg_db, audit_of(lab, table))
    load_orders(pg_db, "('a','x',3,true),('b','x',1,false)", columns)
    with pytest.raises(RuntimeError) as raised:
        run_audit(pg_db, audit_of(lab, table))
    assert "column 'qty': 1" in str(raised.value)
    assert "column 'flag': 1" in str(raised.value)


def test_primary_key_fails_on_nulls_and_on_repeated_combinations(pg_db: psycopg.Connection, lab: Path):
    table = columns_yaml() + "rules:\n  - rule: primary_key\n    columns: [order_id, status]\n"
    load_orders(pg_db, "('a','x',1),('a','y',1),('b',NULL,1)")
    with pytest.raises(RuntimeError, match=r"'primary_key' is broken on table 'orders', column 'order_id, status': 1"):
        run_audit(pg_db, audit_of(lab, table))
    load_orders(pg_db, "('a','x',1),('a','x',2)")
    with pytest.raises(RuntimeError, match="'primary_key' is broken"):
        run_audit(pg_db, audit_of(lab, table))
    load_orders(pg_db, "('a','x',1),('a','y',2)")
    run_audit(pg_db, audit_of(lab, table))


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
def test_row_count_checks_the_bounds(pg_db: psycopg.Connection, lab: Path, bounds: str, count: int, broken: bool):
    table = columns_yaml() + f"rules:\n  - {{rule: row_count, {bounds}}}\n"
    load_orders(pg_db, ",".join("('a','x',1)" for _ in range(count)))
    task = audit_of(lab, table)
    if broken:
        with pytest.raises(RuntimeError, match="'row_count' is broken on table 'orders'"):
            run_audit(pg_db, task)
    else:
        run_audit(pg_db, task)


def test_a_custom_sql_rule_is_broken_when_its_query_returns_rows(pg_db: psycopg.Connection, lab: Path):
    table = (
        columns_yaml()
        + f"rules:\n  - rule: sql\n    sql: |\n      SELECT order_id FROM {SCHEMA}.orders WHERE qty < 0;\n"
    )
    load_orders(pg_db, "('a','x',1)")
    run_audit(pg_db, audit_of(lab, table))
    load_orders(pg_db, "('a','x',-1),('b','x',-5)")
    with pytest.raises(RuntimeError, match="quality rule 'sql' is broken on table 'orders': 2"):
        run_audit(pg_db, audit_of(lab, table))


def test_a_broken_warning_is_logged_and_the_audit_succeeds(
    pg_db: psycopg.Connection, lab: Path, caplog: pytest.LogCaptureFixture
):
    table = columns_yaml(order_id_rules="- {rule: not_null, severity: warning}\n")
    load_orders(pg_db, "(NULL,'x',1)")
    with caplog.at_level(logging.WARNING):
        run_audit(pg_db, audit_of(lab, table))
    assert "quality rule 'not_null' is broken on table 'orders', column 'order_id': 1" in caplog.text


def test_all_broken_errors_are_reported_together_and_warnings_do_not_fail(
    pg_db: psycopg.Connection, lab: Path, caplog: pytest.LogCaptureFixture
):
    table = columns_yaml(
        order_id_rules="- not_null\n",
        status_rules="- {rule: accepted_values, values: [open], severity: warning}\n",
        qty_rules="- not_null\n",
    )
    load_orders(pg_db, "(NULL,'lost',NULL)")
    with caplog.at_level(logging.WARNING), pytest.raises(RuntimeError) as raised:
        run_audit(pg_db, audit_of(lab, table))
    assert "column 'order_id'" in str(raised.value)
    assert "column 'qty'" in str(raised.value)
    assert "column 'status'" not in str(raised.value)
    assert "column 'status'" in caplog.text
