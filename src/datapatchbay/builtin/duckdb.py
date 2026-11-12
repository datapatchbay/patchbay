"""The `duckdb` warehouse: the audit of quality rules. Views, masking and grants are not generated yet."""

from collections.abc import Sequence

from datapatchbay.builtin.audit_sql import Dialect, audit_tasks, standard_identifier, standard_literal
from datapatchbay.plugins import AuditTask, DataProductPlan, SqlTask, TablePlan

DUCKDB_DIALECT = Dialect(identifier=standard_identifier, literal=standard_literal)


class DuckDbWarehouse:
    """Produce SQL for DuckDB."""

    def apply_tasks(self, dataproduct: DataProductPlan) -> Sequence[SqlTask]:
        """Return no task: views for output ports on DuckDB are not generated yet.

        DuckDB has no roles and no grants, so what readers mean there is a separate decision (ADR-0020).
        """
        return ()

    def audit_tasks(self, table: TablePlan) -> Sequence[SqlTask | AuditTask]:
        """Return one audit task for the table's quality rules, or none when no rule has to run.

        The tasks, rules and severities are the same as on Postgres (ADR-0010). A table that dbt builds gets none.
        """
        return audit_tasks(table, DUCKDB_DIALECT)
