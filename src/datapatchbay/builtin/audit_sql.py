"""The SQL of quality rules shared by the built-in warehouses: one query per rule that counts the rows that break it.

The queries use only SQL that Postgres and DuckDB both run. What differs between warehouses, the quoting of names and
the writing of values, is a `Dialect` that each warehouse hands in.
"""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from datapatchbay.dbt import DBT_EXECUTOR
from datapatchbay.models.base import Severity
from datapatchbay.models.table import (
    AcceptedValuesRule,
    ColumnRule,
    NotNullRule,
    PrimaryKeyRule,
    RowCountRule,
    SqlRule,
    TableRule,
    UniqueRule,
)
from datapatchbay.plugins import AuditCheck, AuditTask, TablePlan


@dataclass(frozen=True, slots=True)
class Dialect:
    """The parts of the audit SQL that depend on the warehouse.

    Attributes:
        identifier: Quote a schema, table or column name.
        literal: Write a value of an `accepted_values` rule.
    """

    identifier: Callable[[str], str]
    literal: Callable[[str | int | float | bool], str]


def audit_tasks(table: TablePlan, dialect: Dialect) -> Sequence[AuditTask]:
    """Return one audit task for the table's quality rules, or none when no rule has to run.

    A rule with severity `none` is left out, so a table whose rules are all `none` gets no task. The rules of a table
    that dbt builds run as dbt data tests, so such a table gets no audit task either.
    """
    if table.executor == DBT_EXECUTOR:
        return ()
    checks = audit_checks(table, dialect)
    return (AuditTask(f"audit_{table.name}", checks),) if checks else ()


def audit_checks(table: TablePlan, dialect: Dialect) -> tuple[AuditCheck, ...]:
    """Turn the quality rules of a table into checks: column rules in column order, then the rules on the table.

    A bare rule takes the table's default severity, which is already resolved over the cascade. A rule with severity
    `none` produces no check.
    """
    model = table.source.file.model
    relation = f"{dialect.identifier(table.schema)}.{dialect.identifier(table.name)}"
    checks: list[AuditCheck] = []
    for column in model.columns:
        for rule in column.rules:
            checks.extend(_column_check(table, relation, column.name, rule, dialect))
    for rule in model.rules:
        checks.extend(_table_check(table, relation, rule, dialect))
    return tuple(checks)


def _column_check(
    table: TablePlan, relation: str, column: str, rule: ColumnRule, dialect: Dialect
) -> Iterator[AuditCheck]:
    severity = _severity(table, rule.severity)
    if severity is None:
        return
    name = dialect.identifier(column)
    match rule:
        case NotNullRule():
            sql = f"SELECT count(*) FROM {relation} WHERE {name} IS NULL"
        case UniqueRule():
            sql = _repeated(relation, [name])
        case AcceptedValuesRule():
            listed = ", ".join(dialect.literal(value) for value in rule.values)
            sql = f"SELECT count(*) FROM {relation} WHERE {name} IS NOT NULL AND {name} NOT IN ({listed})"
    yield AuditCheck(rule.rule, table.name, column, severity, sql)


def _table_check(table: TablePlan, relation: str, rule: TableRule, dialect: Dialect) -> Iterator[AuditCheck]:
    severity = _severity(table, rule.severity)
    if severity is None:
        return
    column = None
    match rule:
        case PrimaryKeyRule():
            names = [dialect.identifier(column) for column in rule.columns]
            any_null = " OR ".join(f"{name} IS NULL" for name in names)
            sql = f"SELECT (SELECT count(*) FROM {relation} WHERE {any_null}) + ({_repeated(relation, names)})"
            column = ", ".join(rule.columns)
        case RowCountRule():
            bounds = []
            if rule.min is not None:
                bounds.append(f"n < {rule.min}")
            if rule.max is not None:
                bounds.append(f"n > {rule.max}")
            sql = (
                f"SELECT CASE WHEN {' OR '.join(bounds)} THEN 1 ELSE 0 END "
                f"FROM (SELECT count(*) AS n FROM {relation}) AS counted"
            )
        case SqlRule():
            query = rule.sql.strip().rstrip(";").rstrip()
            sql = f"SELECT count(*) FROM (\n{query}\n) AS violations"
    yield AuditCheck(rule.rule, table.name, column, severity, sql)


def _repeated(relation: str, names: Sequence[str]) -> str:
    """Count the values (or combinations) that occur more than once; a null never counts as repeated."""
    listed = ", ".join(names)
    present = " AND ".join(f"{name} IS NOT NULL" for name in names)
    return (
        f"SELECT count(*) FROM (SELECT 1 FROM {relation} WHERE {present} "
        f"GROUP BY {listed} HAVING count(*) > 1) AS repeated"
    )


def _severity(table: TablePlan, rule_severity: Severity | None) -> Literal["error", "warning"] | None:
    severity = rule_severity or table.severity
    if severity == "none":
        return None
    return severity


def standard_identifier(name: str) -> str:
    """Quote a name the standard SQL way, which Postgres and DuckDB both read."""
    return '"' + name.replace('"', '""') + '"'


def standard_literal(value: str | int | float | bool) -> str:
    """Write a value the standard SQL way, which Postgres and DuckDB both read."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return repr(value)
