"""The `postgres` warehouse. Its SQL for views, masking, grants and audits arrives with later releases."""

from collections.abc import Sequence

from datapatchbay.plugins import DataProductPlan, SqlTask, TablePlan


class PostgresWarehouse:
    """Produce SQL for PostgreSQL. It writes no statements yet, so a DAG ends after the last table."""

    def apply_tasks(self, dataproduct: DataProductPlan) -> Sequence[SqlTask]:
        """Return no tasks yet."""
        return ()

    def audit_tasks(self, table: TablePlan) -> Sequence[SqlTask]:
        """Return no tasks yet."""
        return ()
