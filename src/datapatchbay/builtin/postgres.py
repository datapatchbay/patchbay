"""The `postgres` warehouse. Its SQL for audits arrives with a later release."""

from collections.abc import Sequence

from datapatchbay.builtin.postgres_access import access_sql
from datapatchbay.plugins import DataProductPlan, SqlTask, TablePlan


class PostgresWarehouse:
    """Produce SQL for PostgreSQL."""

    def apply_tasks(self, dataproduct: DataProductPlan) -> Sequence[SqlTask]:
        """Return one task that applies the views, masking and grants of every output port."""
        statements = access_sql(dataproduct)
        return (SqlTask("apply_access", statements),) if statements else ()

    def audit_tasks(self, table: TablePlan) -> Sequence[SqlTask]:
        """Return no tasks yet."""
        return ()
