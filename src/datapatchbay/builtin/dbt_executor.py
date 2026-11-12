"""The `dbt` executor: a table is built by a dbt model in the data product's `models/` folder (ADR-0015)."""

from datapatchbay.plugins import DbtCall, TablePlan, UnsupportedCombinationError


class DbtExecutor:
    """Build a table with a dbt model, by a `dbt build` of the models of its data product."""

    def call(self, table: TablePlan) -> DbtCall:
        """Return the `dbt build` of the data product's `models/` folder.

        Raises:
            UnsupportedCombinationError: If the plan holds no dbt location.
        """
        location = table.dbt
        if location is None:
            raise UnsupportedCombinationError(f"table '{table.name}' has no dbt location to build from")
        return DbtCall(select=location.models, project_dir=location.project_dir, profiles_dir=location.profiles_dir)
