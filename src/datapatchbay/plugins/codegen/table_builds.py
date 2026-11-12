"""What the orchestrators that write Python share: how each table is built, and rendering its build.

Tables built one by one run in plan order. Tables of an executor that builds in a batch (`BatchesBuilds`) run together,
in one task per batch after the others, so every orchestrator refuses the same combinations with the same words.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from datapatchbay.plugins import (
    AuditTask,
    BatchesBuilds,
    BuildCall,
    BuildTask,
    DataProductPlan,
    GenerationContext,
    OwnsQualityRules,
    RenderedTask,
    RenderKind,
    SqlTask,
    TablePlan,
    UnsupportedCombinationError,
)


@dataclass(frozen=True, slots=True)
class Batch:
    """The tables of a data product that one executor builds together.

    Attributes:
        key: The executor's `batch_key`; the task of the batch is `build_<key>`.
        tables: The tables, in plan order. They share one call and one runtime.
        call: The one call that builds them all.
    """

    key: str
    tables: tuple[TablePlan, ...]
    call: BuildCall

    @property
    def task_id(self) -> str:
        """The identifier of the batch's build task."""
        return f"build_{self.key}"

    @property
    def where(self) -> str:
        """What the batch is for, in an error message."""
        return f"tables built by {self.key}"


@dataclass(frozen=True, slots=True)
class TableBuilds:
    """The tables of a data product, split by how they are built.

    Attributes:
        calls: What each executor asks for, by table name.
        python_tables: The tables built one by one, in plan order, which is a topological order.
        batches: The tables built together, one batch per `batch_key`, sorted by key.
    """

    calls: Mapping[str, BuildCall]
    python_tables: tuple[TablePlan, ...]
    batches: tuple[Batch, ...]


def plan_builds(plan: DataProductPlan, context: GenerationContext) -> TableBuilds:
    """Ask each table's executor how to build it, split the tables and refuse what cannot run.

    Args:
        plan: The data product.
        context: The executors of its tables.

    Returns:
        The calls and the tables split into the tables built one by one and the batches.

    Raises:
        UnsupportedCombinationError: If a table needs a table of a batch it is not in, or the tables of a batch do not
            all have the same runtime.
    """
    calls = {table.name: context.executors[table.executor].call(table) for table in plan.tables}
    keys = {
        table.name: executor.batch_key
        for table in plan.tables
        if isinstance(executor := context.executors[table.executor], BatchesBuilds)
    }
    python_tables = tuple(table for table in plan.tables if table.name not in keys)
    for table in plan.tables:
        for need in table.needs:
            if need in keys and keys[need] != keys.get(table.name):
                raise UnsupportedCombinationError(
                    f"table '{table.name}' needs table '{need}', which {keys[need]} builds after the Python tables; "
                    f"{keys[need]} tables cannot be needed"
                )
    batches = []
    for key in sorted(set(keys.values())):
        tables = tuple(table for table in plan.tables if keys.get(table.name) == key)
        for table in tables:
            if table.runtime != tables[0].runtime:
                raise UnsupportedCombinationError(
                    f"tables '{tables[0].name}' and '{table.name}' are built by {key} in one task, "
                    f"but their runtimes are '{tables[0].runtime}' and '{table.runtime}'"
                )
        batches.append(Batch(key, tables, calls[tables[0].name]))
    return TableBuilds(calls=calls, python_tables=python_tables, batches=tuple(batches))


def warehouse_audits(context: GenerationContext, table: TablePlan) -> Sequence[SqlTask | AuditTask]:
    """Return the tasks of the warehouse that audit a table, none when the table's executor runs the rules itself.

    Args:
        context: The warehouse and the executors of the data product's tables.
        table: The built table.
    """
    executor = context.executors[table.executor]
    if isinstance(executor, OwnsQualityRules) and executor.owns_quality_rules(table):
        return ()
    warehouse = context.warehouse
    return warehouse.audit_tasks(table) if warehouse is not None else ()


def render_build(
    context: GenerationContext,
    orchestrator: str,
    kind: RenderKind,
    table: TablePlan,
    call: BuildCall,
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
        table: The table to build; for a batch, the first of its tables.
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
