"""What the orchestrators that write Python share: how each table is built, and rendering its build.

Tables built by Python run one by one, in plan order. Tables built by dbt run together, in one `dbt build` after the
Python tables, so every orchestrator refuses the same combinations with the same words.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from datapatchbay.plugins import (
    BuildTask,
    DataProductPlan,
    DbtCall,
    GenerationContext,
    PythonCall,
    RenderedTask,
    RenderKind,
    TablePlan,
    UnsupportedCombinationError,
)


@dataclass(frozen=True, slots=True)
class TableBuilds:
    """The tables of a data product, split by how they are built.

    Attributes:
        calls: What each executor asks for, by table name.
        python_tables: The tables built by a `PythonCall`, in plan order, which is a topological order.
        dbt_tables: The tables built by a `DbtCall`, in plan order. They share one `dbt build`.
    """

    calls: Mapping[str, PythonCall | DbtCall]
    python_tables: tuple[TablePlan, ...]
    dbt_tables: tuple[TablePlan, ...]

    @property
    def dbt_call(self) -> DbtCall | None:
        """The call of the one `dbt build`, or `None` when no table is built by dbt."""
        if not self.dbt_tables:
            return None
        call = self.calls[self.dbt_tables[0].name]
        assert isinstance(call, DbtCall)
        return call


def plan_builds(plan: DataProductPlan, context: GenerationContext) -> TableBuilds:
    """Ask each table's executor how to build it, split the tables and refuse what cannot run.

    Args:
        plan: The data product.
        context: The executors of its tables.

    Returns:
        The calls and the tables split into Python tables and dbt tables.

    Raises:
        UnsupportedCombinationError: If a Python table needs a table that dbt builds, or the tables built by dbt do not
            all have the same runtime.
    """
    calls = {table.name: context.executors[table.executor].call(table) for table in plan.tables}
    dbt_names = {name for name, call in calls.items() if isinstance(call, DbtCall)}
    python_tables = tuple(table for table in plan.tables if table.name not in dbt_names)
    dbt_tables = tuple(table for table in plan.tables if table.name in dbt_names)
    for table in python_tables:
        for need in table.needs:
            if need in dbt_names:
                raise UnsupportedCombinationError(
                    f"table '{table.name}' needs table '{need}', which dbt builds after the Python tables; "
                    "dbt tables cannot be needed"
                )
    for table in dbt_tables:
        if table.runtime != dbt_tables[0].runtime:
            raise UnsupportedCombinationError(
                f"tables '{dbt_tables[0].name}' and '{table.name}' are built by dbt in one task, "
                f"but their runtimes are '{dbt_tables[0].runtime}' and '{table.runtime}'"
            )
    return TableBuilds(calls=calls, python_tables=python_tables, dbt_tables=dbt_tables)


def render_build(
    context: GenerationContext,
    orchestrator: str,
    kind: RenderKind,
    table: TablePlan,
    call: PythonCall | DbtCall,
    *,
    task_id: str,
    where: str,
    variable: str,
) -> RenderedTask:
    """Have the table's runtime render its build.

    Args:
        context: The runtimes of the data product's tables.
        orchestrator: Name of the orchestrator plugin the code is for, used in error messages only.
        kind: The render kind the orchestrator declares.
        table: The table to build; for a dbt call, the first of the tables that dbt builds.
        call: What the executor asked for.

    Keyword Args:
        task_id: Identifier of the build task.
        where: What the build is for, for the error message, such as `table 'orders'`.
        variable: The name that the runtime must assign the build to.

    Raises:
        UnsupportedCombinationError: If the runtime cannot render the build, or cannot write a param as Python.
    """
    task = BuildTask(task_id=task_id, table=table, call=call)
    runtime = context.runtimes[table.runtime]
    if kind not in runtime.render_kinds:
        raise UnsupportedCombinationError(
            f"the {table.runtime} runtime cannot render tasks for orchestrator '{orchestrator}'"
        )
    try:
        return runtime.render_build_task(task, kind=kind, variable=variable)
    except ValueError as exc:
        raise UnsupportedCombinationError(f"{where}: {exc}") from exc
