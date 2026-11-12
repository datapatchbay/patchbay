"""The `postgres` warehouse: SQL for views, masking and grants, and the audit of quality rules."""

from collections.abc import Sequence

from datapatchbay.integrations.postgres.access import access_sql
from datapatchbay.plugins import AuditTask, DataProductPlan, SqlTask, TablePlan
from datapatchbay.plugins.sql import Dialect, audit_tasks, standard_identifier, standard_literal

POSTGRES_DIALECT = Dialect(identifier=standard_identifier, literal=standard_literal)


class PostgresWarehouse:
    """Produce SQL for PostgreSQL."""

    def apply_tasks(self, dataproduct: DataProductPlan) -> Sequence[SqlTask]:
        """Return one task that applies the views, masking and grants of every output port."""
        statements = access_sql(dataproduct)
        return (SqlTask("apply_access", statements),) if statements else ()

    def audit_tasks(self, table: TablePlan) -> Sequence[SqlTask | AuditTask]:
        """Return one audit task for the table's quality rules, or none when no rule has to run.

        A rule with severity `none` is left out, so a table whose rules are all `none` gets no task.
        """
        return audit_tasks(table, POSTGRES_DIALECT)
