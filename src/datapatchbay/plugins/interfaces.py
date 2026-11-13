"""The plugin interfaces: the four extension points of ADR-0009.

There are four extension points. Each one is a `Protocol`, and a plugin is any object that has the same methods:

- An **orchestrator** turns a data product's plan into the files the orchestrator runs, and decides when the data
  product runs. It composes the tasks that the other three contribute.
- An **executor** says what has to be called to build a table.
- A **runtime** renders the build task, the place where an executor's code runs.
- A **warehouse** produces the SQL that the orchestrator runs through its own connection (ADR-0001).

An executor may also offer **capabilities**: small `runtime_checkable` protocols below that the core checks with
`isinstance` on the executor plugin. The core never asks which executor it is. A capability is optional; an executor
that lacks it is simply not asked.

Any of the four may also declare its own **settings** (`DeclaresSettings`, ADR-0025): a root-level section of
`datapatchbay.yaml` named after the plugin, and naming templates under `conventions.names`.

The interface is not stable in milestone 1.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from datapatchbay.files.repomodel import DataProduct, Repo, Table
from datapatchbay.plugins.plan import DataProductPlan, NewTable, PlannedRepo, TablePlan
from datapatchbay.plugins.tasks import (
    AuditTask,
    BuildCall,
    BuildTask,
    GeneratedFile,
    RenderedTask,
    ScaffoldedTable,
    SqlTask,
)
from datapatchbay.problems import Problem

if TYPE_CHECKING:
    from datapatchbay.settings.effective import EffectiveSettings

__all__ = [
    "BatchesBuilds",
    "ChecksDataProducts",
    "ChecksPlans",
    "ChecksTables",
    "CommittedOutput",
    "DeclaredSettings",
    "DeclaresSettings",
    "Executor",
    "GenerationContext",
    "NamingTemplate",
    "Orchestrator",
    "OwnsQualityRules",
    "Runtime",
    "ScaffoldsTables",
    "UnsupportedCombinationError",
    "Warehouse",
    "WritesCommittedFiles",
]


@dataclass(frozen=True, slots=True)
class NamingTemplate:
    """A naming template that a plugin adds under `conventions.names` (ADR-0006, ADR-0025).

    Attributes:
        default: The template when the repo sets none.
        description: What the name is for; it is the description in the JSON Schema.
        placeholders: The placeholders the template may use besides the usual `{name}`, `{kind.prefix}` and
            `{kind.name}`, such as `("dataproduct", "table")`.
    """

    default: str
    description: str
    placeholders: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DeclaredSettings:
    """What a plugin adds to the settings: a root-level section and naming templates (ADR-0025).

    Attributes:
        section: The model of the section, which `datapatchbay.yaml` holds under the plugin's name. It rejects
            unknown keys, gives every field a description and defaults every field to `None`: a field that is `None`
            takes its value from `defaults`. `None` when the plugin has no section.
        description: Describes the section in the JSON Schema.
        defaults: The default value of each field of the section; a plain YAML value per key.
        naming_templates: The naming templates, by name, that the plugin adds under `conventions.names`.
    """

    section: type[BaseModel] | None = None
    description: str = ""
    defaults: Mapping[str, Any] = field(default_factory=dict)
    naming_templates: Mapping[str, NamingTemplate] = field(default_factory=dict)


@runtime_checkable
class DeclaresSettings(Protocol):
    """Capability of any plugin: it declares settings of its own, which the core reads without knowing the plugin.

    The section is named after the plugin's entry point name and is read at the root only, with no cascade. The
    core refuses a plugin whose section or template would collide with a core setting or with another plugin.
    The resolved section, an instance of `section`, is on the plans in `plugin_settings`, by plugin name.

    Attributes:
        declared_settings: The section and naming templates of this plugin.
    """

    declared_settings: DeclaredSettings


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

    def call(self, table: TablePlan) -> BuildCall:
        """Return how to call the table's build, such as a Python function."""
        ...


@runtime_checkable
class WritesCommittedFiles(Protocol):
    """Capability: the executor produces files that are committed in the repo, next to the data products.

    The core asks every installed executor with this capability, whether or not a table uses it, because files can
    be left over from an earlier run. `dpb validate` compares the output with the disk, `dpb generate` writes it.
    """

    def committed_output(self, planned: PlannedRepo) -> "CommittedOutput":
        """Work out the committed output of the planned repo, without writing anything."""
        ...


class CommittedOutput(Protocol):
    """The value that `WritesCommittedFiles.committed_output` returns: one value that is both written and diffed.

    Attributes:
        orphans: Generated files that nothing produces any more, relative to the repo root, sorted.
        error: Why the output cannot be written, or `None`. `dpb generate` fails with it before it writes anything.
    """

    orphans: tuple[PurePosixPath, ...]
    error: str | None

    def problems(self) -> list[Problem]:
        """Diff the output with the files on disk; empty when they are in step."""
        ...

    def write(self) -> tuple[PurePosixPath, ...]:
        """Write the files, delete the orphans and return the files written, relative to the repo root."""
        ...


@runtime_checkable
class ChecksDataProducts(Protocol):
    """Capability: the executor adds stage 1 checks of a data product's files, whichever executor its tables use.

    The core calls it for every data product of the repo, in repo order, before the checks of its tables.
    """

    def check_dataproduct(self, repo: Repo, dataproduct: DataProduct) -> Sequence[Problem]:
        """Return the problems with the files of one data product."""
        ...


@runtime_checkable
class ChecksTables(Protocol):
    """Capability: the executor adds stage 1 checks of the table files it builds.

    The core calls it for each table whose executor, resolved over the settings cascade, is this plugin, in repo
    order. One plugin object serves a whole validation, so it may keep what it saw (names used so far).
    """

    def check_table(self, settings: "EffectiveSettings", dataproduct: DataProduct, table: Table) -> Sequence[Problem]:
        """Return the problems with one table file."""
        ...


@runtime_checkable
class ChecksPlans(Protocol):
    """Capability: the executor adds stage 2 checks that need the planned repo, such as reading its own outputs.

    The core calls it for every installed executor with this capability, after the repo passed stage 1.
    """

    def check_plans(self, planned: PlannedRepo) -> Sequence[Problem]:
        """Return the problems found by comparing the plans with what is on disk."""
        ...


@runtime_checkable
class BatchesBuilds(Protocol):
    """Capability: the executor builds all its tables of a data product in one task.

    The tables of one data product whose executors share a `batch_key` are built by one task named `build_<key>`,
    after the tables that are built one by one. No other table can `needs` a table in a batch, and the tables of a
    batch share one runtime, which must be able to run `call_type`.

    Attributes:
        batch_key: Names the group and its task, such as `dbt` for the task `build_dbt`.
        call_type: The type of call the executor returns, which the runtime must be able to run.
    """

    batch_key: str
    call_type: type

    def call(self, table: TablePlan) -> BuildCall:
        """Return the one call that builds every table of the batch; `table` is the first of them."""
        ...


@runtime_checkable
class OwnsQualityRules(Protocol):
    """Capability: the executor runs the quality rules of its tables itself, so the warehouse audits skip them."""

    def owns_quality_rules(self, table: TablePlan) -> bool:
        """Return whether the executor runs the rules of this table."""
        ...


@runtime_checkable
class ScaffoldsTables(Protocol):
    """Capability: the executor writes the stub of a new table for `dpb new`."""

    def scaffold_table(self, table: NewTable) -> ScaffoldedTable:
        """Return the `build` block of the table file and the files of the new data product that build it."""
        ...


RenderKind = Literal["task", "function"]
"""What build code an orchestrator needs: `task` is an Airflow-style operator or task object, `function` is a plain
Python function with no arguments that the orchestrator calls when the build has to run."""


class Runtime(Protocol):
    """Renders the build task of a table, so it runs in the place this runtime stands for.

    The attributes are class attributes every runtime sets. `dpb validate` reads `needs_image` and `call_types`: it
    reports a table whose resolved `image` is not set when `needs_image` is true, and a batch of tables whose call type
    is not in `call_types`. `dpb generate` reads `render_kinds`: it refuses a runtime on an orchestrator whose
    `render_kind` the runtime does not support.

    Attributes:
        needs_image: Whether the runtime runs a container image, so a table needs a resolved `image`.
        call_types: The types of call the runtime can run.
        render_kinds: The render kinds this runtime can produce code for.
    """

    needs_image: bool
    call_types: tuple[type, ...]
    render_kinds: frozenset[RenderKind]

    def render_build_task(self, task: BuildTask, *, kind: RenderKind, variable: str) -> RenderedTask:
        """Render the build task as code of the given kind.

        Args:
            task: The table's build.

        Keyword Args:
            kind: The render kind the orchestrator needs; one of `render_kinds`.
            variable: The name that the task must be assigned to in `RenderedTask.lines`.

        Raises:
            UnsupportedCombinationError: If this runtime cannot render that kind or cannot run the call.
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
    """Generates the files an orchestrator runs for one data product.

    Attributes:
        render_kind: The kind of build code the generated file needs from a runtime (`task` or `function`).
    """

    render_kind: RenderKind

    def generate(self, plan: DataProductPlan, context: GenerationContext) -> Sequence[GeneratedFile]:
        """Return the files for one data product.

        Raises:
            UnsupportedCombinationError: If the plan cannot be expressed for this orchestrator.
        """
        ...
