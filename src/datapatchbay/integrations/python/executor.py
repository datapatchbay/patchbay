"""The `python` executor: a table is built by calling a Python function with its params."""

from datapatchbay.plugins import PythonCall, TablePlan, UnsupportedCombinationError


class PythonExecutor:
    """Build a table by calling the function named in its entrypoint."""

    def call(self, table: TablePlan) -> PythonCall:
        """Return the call of the table's entrypoint function with the table's params."""
        if table.entrypoint is None or table.function is None:
            raise UnsupportedCombinationError(f"table '{table.name}' has no `build.entrypoint` for the python executor")
        return PythonCall(file=table.entrypoint, function=table.function, params=table.params)
