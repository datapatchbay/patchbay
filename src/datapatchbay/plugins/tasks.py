"""The tasks: what the plugins hand back to the orchestrator, as plain values (ADR-0009).

The calls an executor asks for, the build task a runtime renders, the SQL and audit tasks a warehouse produces and the
files an orchestrator returns. The plan they are made from is in `plan`, the interfaces that make them in `interfaces`.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Literal

from datapatchbay.plugins.plan import TablePlan

__all__ = [
    "AuditCheck",
    "AuditTask",
    "BuildCall",
    "BuildTask",
    "CommandCall",
    "GeneratedFile",
    "PythonCall",
    "RenderedTask",
    "ScaffoldedTable",
    "SqlTask",
]


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
class CommandCall:
    """Run a command on the worker, as an executor asks for when its tool is a program, not a Python function.

    The command is run without a shell, so the runtime expands no variables or globs. It does expand a leading `~` of
    an argument to the home of the worker's user, which a shell would have done.

    Attributes:
        argv: The program and its arguments.
        cwd: The working directory: an absolute path, or the path from the data product folder.
        env: Environment variables to set besides the environment of the worker.
    """

    argv: tuple[str, ...]
    cwd: str = "."
    env: Mapping[str, str] = field(default_factory=dict)


type BuildCall = PythonCall | CommandCall
"""What an executor asks a runtime to run."""


@dataclass(frozen=True, slots=True)
class BuildTask:
    """What a runtime renders: a build and how the executor wants it called.

    For a `PythonCall` the task builds one table. For a `CommandCall` it builds every table of the batch at
    once, and `table` is the first of them, which holds the settings the tables share, such as the runtime.
    """

    task_id: str
    table: TablePlan
    call: BuildCall


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
class AuditCheck:
    """One quality rule, as a query that counts the rows that break it.

    Attributes:
        rule: Name of the rule, such as `not_null`.
        table: Name of the audited table.
        column: The column the rule is on, several joined by `, ` for a primary key, or `None` for a rule on the
            whole table.
        severity: What a broken rule does: `error` fails the task, `warning` is logged. A rule with severity `none`
            is never turned into a check.
        sql: A query that returns one row with one integer: the number of violations. Zero means the rule holds.
    """

    rule: str
    table: str
    column: str | None
    severity: Literal["error", "warning"]
    sql: str


@dataclass(frozen=True, slots=True)
class AuditTask:
    """The quality rules of one table, audited together by one task through the orchestrator's connection.

    The orchestrator runs every check, logs the broken `warning` checks and fails the task if any `error` check is
    broken, naming the rule, the table and the column of each (ADR-0010).

    Attributes:
        task_id: Identifier of the task, unique within the DAG.
        checks: The checks to run, in a fixed order.
    """

    task_id: str
    checks: tuple[AuditCheck, ...]


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
class ScaffoldedTable:
    """What an executor adds to a new table for `dpb new`.

    Attributes:
        build: The `build` block of the table file, or `None` when the executor needs none.
        files: Files for the new data product, by path relative to its folder, such as the stub of the build code.
    """

    build: Mapping[str, Any] | None
    files: Mapping[str, str]
