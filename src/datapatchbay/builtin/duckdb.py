"""The `duckdb` warehouse: views for output ports and the audit of quality rules. It enforces no access (ADR-0021)."""

from collections.abc import Sequence

from datapatchbay.builtin.audit_sql import Dialect, audit_tasks, standard_identifier, standard_literal
from datapatchbay.builtin.port_views import output_ports, view_sql
from datapatchbay.plugins import AuditTask, DataProductPlan, SqlTask, TablePlan

DUCKDB_DIALECT = Dialect(identifier=standard_identifier, literal=standard_literal)


def _masked(name: str) -> str:
    """Select a PII column as NULL of its own type: there are no roles on DuckDB, so nobody reads it (ADR-0021)."""
    return f"CASE WHEN false THEN {name} END AS {name}"


class DuckDbWarehouse:
    """Produce SQL for DuckDB."""

    def apply_tasks(self, dataproduct: DataProductPlan) -> Sequence[SqlTask]:
        """Return one task that applies the views of every output port, or none when there is no output port.

        Each port's schema is dropped and created again, so a table or column that left the table files is gone from
        the next apply. DuckDB has no roles: readers and PII readers are accepted and create no grants, and a PII
        column shows NULL to everyone (ADR-0021).
        """
        statements = []
        for port, tables in output_ports(dataproduct):
            schema = DUCKDB_DIALECT.identifier(port.name)
            statements += [
                f"-- Output port {' '.join(port.name.split())}",
                f"DROP SCHEMA IF EXISTS {schema} CASCADE;",
                f"CREATE SCHEMA {schema};",
                *(view_sql(table, DUCKDB_DIALECT, _masked) for table in tables),
            ]
        return (SqlTask("apply_access", "\n".join(statements)),) if statements else ()

    def audit_tasks(self, table: TablePlan) -> Sequence[SqlTask | AuditTask]:
        """Return one audit task for the table's quality rules, or none when no rule has to run.

        The tasks, rules and severities are the same as on Postgres (ADR-0010). A table that dbt builds gets none.
        """
        return audit_tasks(table, DUCKDB_DIALECT)
