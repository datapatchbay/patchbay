"""The `dbt` executor: a table is built by a dbt model in the data product's `models/` folder (ADR-0015)."""

from datapatchbay.plugins import PythonCall, TablePlan, UnsupportedCombinationError


class DbtExecutor:
    """Build a table with a dbt model. `dpb validate` accepts such tables; running them in a DAG comes later."""

    def call(self, table: TablePlan) -> PythonCall:
        """Report that a dbt table cannot be put in a generated DAG yet."""
        raise UnsupportedCombinationError(
            f"table '{table.name}' is built by dbt, and `dpb generate` cannot run dbt models in a DAG yet"
        )
