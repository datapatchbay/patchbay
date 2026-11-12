"""The `postgres` warehouse: SQL for views, masking and grants, and the audit of quality rules."""

from collections.abc import Sequence

from datapatchbay.builtin.postgres_access import access_sql
from datapatchbay.builtin.postgres_audit import audit_checks
from datapatchbay.dbt import DBT_EXECUTOR
from datapatchbay.plugins import AuditTask, DataProductPlan, SqlTask, TablePlan


class PostgresWarehouse:
    """Produce SQL for PostgreSQL."""

    def apply_tasks(self, dataproduct: DataProductPlan) -> Sequence[SqlTask]:
        """Return one task that applies the views, masking and grants of every output port."""
        statements = access_sql(dataproduct)
        return (SqlTask("apply_access", statements),) if statements else ()

    def audit_tasks(self, table: TablePlan) -> Sequence[SqlTask | AuditTask]:
        """Return one audit task for the table's quality rules, or none when no rule has to run.

        A rule with severity `none` is left out, so a table whose rules are all `none` gets no task. The rules of a
        table that dbt builds run as dbt data tests, so such a table gets no audit task either.
        """
        if table.executor == DBT_EXECUTOR:
            return ()
        checks = audit_checks(table)
        return [AuditTask(f"audit_{table.name}", checks)] if checks else ()
