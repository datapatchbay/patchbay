"""The `python` executor: a table is built by calling a Python function with its params."""

from datapatchbay.plugins import PythonCall, TablePlan


class PythonExecutor:
    """Build a table by calling the function named in its entrypoint."""

    def call(self, table: TablePlan) -> PythonCall:
        """Return the call of the table's entrypoint function with the table's params."""
        return PythonCall(file=table.entrypoint, function=table.function, params=table.params)
