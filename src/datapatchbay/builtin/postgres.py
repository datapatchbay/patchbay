"""The `postgres` warehouse. Its SQL for views, masking and grants arrives with later releases."""

from collections.abc import Sequence

from datapatchbay.builtin.postgres_audit import audit_checks
from datapatchbay.plugins import AuditTask, DataProductPlan, SqlTask, TablePlan


class PostgresWarehouse:
    """Produce SQL for PostgreSQL: the audit of quality rules now, views and grants later."""

    def apply_tasks(self, dataproduct: DataProductPlan) -> Sequence[SqlTask]:
        """Return no tasks yet."""
        return ()

    def audit_tasks(self, table: TablePlan) -> Sequence[SqlTask | AuditTask]:
        """Return one audit task for the table's quality rules, or none when no rule has to run.

        A rule with severity `none` is left out, so a table whose rules are all `none` gets no task.
        """
        checks = audit_checks(table)
        return [AuditTask(f"audit_{table.name}", checks)] if checks else ()
