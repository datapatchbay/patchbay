"""The plugin interface: what `dpb generate` hands to plugins and what plugins hand back (ADR-0009).

There are four extension points. Each one is a `Protocol`, and a plugin is any object that has the same methods:

- An **orchestrator** turns a data product's plan into the files the orchestrator runs, and decides when the data
  product runs. It composes the tasks that the other three contribute.
- An **executor** says what has to be called to build a table.
- A **runtime** renders the build task, the place where an executor's code runs.
- A **warehouse** produces the SQL that the orchestrator runs through its own connection (ADR-0001).

The interface is not stable in milestone 1.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from datapatchbay.models.base import Severity
from datapatchbay.repomodel import DataProduct, Port, Table

__all__ = [
    "BuildTask",
    "DataProductPlan",
    "Executor",
    "GeneratedFile",
    "GenerationContext",
    "Orchestrator",
    "PythonCall",
    "RenderedTask",
    "Runtime",
    "SourceSchedule",
    "SqlTask",
    "TablePlan",
    "UnsupportedCombinationError",
    "Warehouse",
]


class UnsupportedCombinationError(Exception):
    """Raised by a plugin that cannot work with the plugins or the build it is combined with.

    `dpb generate` reports it as a failure that names the data product.
    """


@dataclass(frozen=True, slots=True)
class TablePlan:
    """One table to build, with its settings resolved over the cascade.

    Attributes:
        dataproduct: Folder name of the data product the table belongs to.
        port: Name of the port the table is in.
        name: Name of the table.
        entrypoint: The file of the build function, relative to the data product folder.
        function: Name of the build function.
        params: Parameters passed to the function.
        needs: Names of the tables of the same data product that are built first.
        executor: Name of the executor plugin.
        runtime: Name of the runtime plugin.
        image: Container image for container runtimes, or `None`.
        container: Free-form settings for the container task, as written in the files; dpb does not read them.
        severity: Default severity of the table's quality rules.
        port_source: The loaded port, for plugins that need its contract or access policy.
        source: The loaded table, for plugins that need its columns and quality rules.
    """

    dataproduct: str
    port: str
    name: str
    entrypoint: PurePosixPath
    function: str
    params: Mapping[str, Any]
    needs: tuple[str, ...]
    executor: str
    runtime: str
    image: str | None
    severity: Severity
    port_source: Port
    source: Table
    container: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceSchedule:
    """A source input port and the cron expression at which its source delivers data."""

    port: str
    cron: str


@dataclass(frozen=True, slots=True)
class DataProductPlan:
    """Everything an orchestrator needs to generate one data product's DAG.

    Attributes:
        folder: Folder name of the data product, which is also its DAG id.
        name: Name of the data product.
        owner: The owner, free text.
        directory: Absolute path of the data product folder.
        orchestrator: Name of the orchestrator plugin.
        warehouse: Name of the warehouse plugin.
        connection: Name of the orchestrator's connection to the warehouse.
        tables: Every table, ordered so that a table comes after the tables in its `needs`.
        source_schedules: The input ports fed by a source, sorted by port name.
        reads: Names of the output ports of other data products that this data product reads, sorted.
        outputs: Names of the output ports, sorted.
        source: The loaded data product, for plugins that need its files.
    """

    folder: str
    name: str
    owner: str
    directory: Path
    orchestrator: str
    warehouse: str
    connection: str
    tables: tuple[TablePlan, ...]
    source_schedules: tuple[SourceSchedule, ...]
    reads: tuple[str, ...]
    outputs: tuple[str, ...]
    source: DataProduct


@dataclass(frozen=True, slots=True)
class PythonCall:
    """Call a Python function with keyword parameters, as the python executor asks for.

    Attributes:
        file: The file that holds the function, relative to the data product folder.
        function: Name of the function.
        params: Keyword parameters, as plain YAML values.
    """

    file: PurePosixPath
    function: str
    params: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class BuildTask:
    """What a runtime renders: one table's build and how the executor wants it called."""

    task_id: str
    table: TablePlan
    call: PythonCall


@dataclass(frozen=True, slots=True)
class RenderedTask:
    """Source code for one task, in the language of the orchestrator it was rendered for.

    The orchestrator places the pieces: `imports` at the top of the file once, `helpers` at module level once and
    `lines` inside the DAG, where `lines` must assign the task to the variable it was asked to use.

    Attributes:
        imports: Import statements. Identical statements from several tasks are written once.
        helpers: Module-level code that `lines` use. Identical blocks from several tasks are written once.
        lines: Statements that create the task.
    """

    imports: tuple[str, ...] = ()
    helpers: tuple[str, ...] = ()
    lines: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SqlTask:
    """SQL that the orchestrator runs through its connection to the warehouse.

    Attributes:
        task_id: Identifier of the task, unique within the DAG.
        sql: The statements to run. dpb never runs them itself (ADR-0001).
    """

    task_id: str
    sql: str


@dataclass(frozen=True, slots=True)
class GeneratedFile:
    """A file for the output folder.

    Attributes:
        path: Where the file goes, relative to the output folder.
        content: The text of the file, which must be the same for the same input.
    """

    path: PurePosixPath
    content: str


@dataclass(frozen=True, slots=True)
class GenerationContext:
    """What the core hands an orchestrator besides the plan.

    Attributes:
        root: Absolute path of the repo root.
        output_dir: Absolute path of the output folder.
        executors: The executor plugins that the data product's tables use, by name.
        runtimes: The runtime plugins that the data product's tables use, by name.
        warehouse: The warehouse plugin of the data product.
    """

    root: Path
    output_dir: Path
    executors: Mapping[str, "Executor"] = field(default_factory=dict)
    runtimes: Mapping[str, "Runtime"] = field(default_factory=dict)
    warehouse: "Warehouse | None" = None


class Executor(Protocol):
    """Says what has to be called to build a table."""

    def call(self, table: TablePlan) -> PythonCall:
        """Return how to call the table's build code."""
        ...


class Runtime(Protocol):
    """Renders the build task of a table, so it runs in the place this runtime stands for.

    A runtime that runs a container image may set the class attribute `needs_image = True`; `dpb validate` then
    reports a table whose resolved `image` is not set.
    """

    def render_build_task(self, task: BuildTask, *, orchestrator: str, variable: str) -> RenderedTask:
        """Render the build task for an orchestrator.

        Args:
            task: The table's build.

        Keyword Args:
            orchestrator: Name of the orchestrator plugin the code is for.
            variable: The name that the task must be assigned to in `RenderedTask.lines`.

        Raises:
            UnsupportedCombinationError: If this runtime cannot run on that orchestrator or cannot run the call.
        """
        ...


class Warehouse(Protocol):
    """Produces SQL for a warehouse. It never connects to it (ADR-0001)."""

    def apply_tasks(self, dataproduct: DataProductPlan) -> Sequence[SqlTask]:
        """Return the tasks that run after every table is built, such as views, masking and grants."""
        ...

    def audit_tasks(self, table: TablePlan) -> Sequence[SqlTask]:
        """Return the tasks that audit a table after it is built."""
        ...


class Orchestrator(Protocol):
    """Generates the files an orchestrator runs for one data product."""

    def generate(self, plan: DataProductPlan, context: GenerationContext) -> Sequence[GeneratedFile]:
        """Return the files for one data product.

        Raises:
            UnsupportedCombinationError: If the plan cannot be expressed for this orchestrator.
        """
        ...
