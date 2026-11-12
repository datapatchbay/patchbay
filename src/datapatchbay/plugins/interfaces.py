"""The plugin interfaces: the four extension points of ADR-0009.

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
from pathlib import Path
from typing import Protocol

from datapatchbay.plugins.plan import DataProductPlan, TablePlan
from datapatchbay.plugins.tasks import AuditTask, BuildTask, DbtCall, GeneratedFile, PythonCall, RenderedTask, SqlTask

__all__ = [
    "Executor",
    "GenerationContext",
    "Orchestrator",
    "Runtime",
    "UnsupportedCombinationError",
    "Warehouse",
]


class UnsupportedCombinationError(Exception):
    """Raised by a plugin that cannot work with the plugins or the build it is combined with.

    `dpb generate` reports it as a failure that names the data product.
    """


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

    def call(self, table: TablePlan) -> PythonCall | DbtCall:
        """Return how to call the table's build: a Python function, or a dbt build of the data product's models."""
        ...


class Runtime(Protocol):
    """Renders the build task of a table, so it runs in the place this runtime stands for.

    Both flags are class attributes every runtime sets. `dpb validate` reads them: it reports a table whose resolved
    `image` is not set when `needs_image` is true, and a table built by dbt when `runs_dbt` is false.

    Attributes:
        needs_image: Whether the runtime runs a container image, so a table needs a resolved `image`.
        runs_dbt: Whether the runtime can run `dbt build`.
    """

    needs_image: bool
    runs_dbt: bool

    def render_build_task(self, task: BuildTask, *, orchestrator: str, variable: str) -> RenderedTask:
        """Render the build task for an orchestrator.

        Args:
            task: The table's build.

        Keyword Args:
            orchestrator: Name of the orchestrator plugin the code is for.
            variable: The name that the task must be assigned to in `RenderedTask.lines`.

        Raises:
            UnsupportedCombinationError: If this runtime cannot run on that orchestrator or cannot run the call.
            ValueError: If a param or setting of the table cannot be written into the task, such as a value that is
                not a plain YAML value. The orchestrator reports it as an `UnsupportedCombinationError` naming
                the table.
        """
        ...


class Warehouse(Protocol):
    """Produces SQL for a warehouse. It never connects to it (ADR-0001)."""

    def apply_tasks(self, dataproduct: DataProductPlan) -> Sequence[SqlTask]:
        """Return the tasks that run after every table is built, such as views, masking and grants."""
        ...

    def audit_tasks(self, table: TablePlan) -> Sequence[SqlTask | AuditTask]:
        """Return the tasks that audit a table after it is built.

        An `AuditTask` carries the table's quality rules with their severity; a `SqlTask` is plain SQL that fails
        when it raises.
        """
        ...


class Orchestrator(Protocol):
    """Generates the files an orchestrator runs for one data product."""

    def generate(self, plan: DataProductPlan, context: GenerationContext) -> Sequence[GeneratedFile]:
        """Return the files for one data product.

        Raises:
            UnsupportedCombinationError: If the plan cannot be expressed for this orchestrator.
        """
        ...
