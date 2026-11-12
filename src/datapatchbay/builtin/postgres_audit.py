"""The SQL of the Postgres warehouse for quality rules: one query per rule that counts the rows that break it."""

from collections.abc import Iterator, Sequence
from typing import Literal

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
from datapatchbay.plugins import AuditCheck, TablePlan


def audit_checks(table: TablePlan) -> tuple[AuditCheck, ...]:
    """Turn the quality rules of a table into checks: column rules in column order, then the rules on the table.

    A bare rule takes the table's default severity, which is already resolved over the cascade. A rule with severity
    `none` produces no check.
    """
    model = table.source.file.model
    relation = f"{_identifier(table.schema)}.{_identifier(table.name)}"
    checks: list[AuditCheck] = []
    for column in model.columns:
        for rule in column.rules:
            checks.extend(_column_check(table, relation, column.name, rule))
    for rule in model.rules:
        checks.extend(_table_check(table, relation, rule))
    return tuple(checks)


def _column_check(table: TablePlan, relation: str, column: str, rule: ColumnRule) -> Iterator[AuditCheck]:
    severity = _severity(table, rule.severity)
    if severity is None:
        return
    name = _identifier(column)
    match rule:
        case NotNullRule():
            sql = f"SELECT count(*) FROM {relation} WHERE {name} IS NULL"
        case UniqueRule():
            sql = _repeated(relation, [name])
        case AcceptedValuesRule():
            listed = ", ".join(_literal(value) for value in rule.values)
            sql = f"SELECT count(*) FROM {relation} WHERE {name} IS NOT NULL AND {name} NOT IN ({listed})"
    yield AuditCheck(rule.rule, table.name, column, severity, sql)


def _table_check(table: TablePlan, relation: str, rule: TableRule) -> Iterator[AuditCheck]:
    severity = _severity(table, rule.severity)
    if severity is None:
        return
    column = None
    match rule:
        case PrimaryKeyRule():
            names = [_identifier(column) for column in rule.columns]
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


def _identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _literal(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return repr(value)
