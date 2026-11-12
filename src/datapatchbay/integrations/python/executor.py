"""The `python` executor: a table is built by calling a Python function with its params."""

from collections.abc import Sequence

from datapatchbay.files.repomodel import DataProduct, Table
from datapatchbay.plugins import NewTable, PythonCall, ScaffoldedTable, TablePlan, UnsupportedCombinationError
from datapatchbay.problems import Problem
from datapatchbay.settings.effective import EffectiveSettings

_STUB = '''"""Build code of the table `{table}`."""


def build() -> None:
    """Build the table `{table}`. Replace this stub with the code that writes it to the warehouse."""
    raise NotImplementedError("write the build code of the table '{table}'")
'''


class PythonExecutor:
    """Build a table by calling the function named in its entrypoint."""

    def call(self, table: TablePlan) -> PythonCall:
        """Return the call of the table's entrypoint function with the table's params."""
        if table.entrypoint is None or table.function is None:
            raise UnsupportedCombinationError(f"table '{table.name}' has no `build.entrypoint` for the python executor")
        return PythonCall(file=table.entrypoint, function=table.function, params=table.params)

    def check_table(self, settings: EffectiveSettings, dataproduct: DataProduct, table: Table) -> Sequence[Problem]:
        """Require a `build` block with an `entrypoint`, because this executor calls it."""
        file = table.file
        build = file.model.build
        if build is None:
            message = (
                f"table '{table.name}' needs a `build` block with an `entrypoint`, because its executor is 'python'"
            )
            return [Problem(file.path, None, message)]
        if build.entrypoint is None:
            message = f"table '{table.name}' needs a `build.entrypoint`, because its executor is 'python'"
            return [Problem(file.path, file.line("build"), message)]
        return []

    def scaffold_table(self, table: NewTable) -> ScaffoldedTable:
        """Return the stub `src/<table>.py` and the `build` block that points at it, with the table's `needs`."""
        build: dict[str, object] = {"entrypoint": f"src/{table.name}.py:build"}
        if table.needs:
            build["needs"] = list(table.needs)
        return ScaffoldedTable(build=build, files={f"src/{table.name}.py": _STUB.format(table=table.name)})
