"""The `local` orchestrator: one standalone Python script per data product, which builds it once when it runs.

The script runs the builds, the audits and then the warehouse's apply SQL, in that order, and stops at the first
failure. It connects to the warehouse itself, through a URL in an environment variable (ADR-0022); `dpb` connects to
nothing (ADR-0001). It does not schedule itself: the schedule of the source input ports is a comment at its top.

The script defines `DATAPRODUCT_DIR` like an Airflow DAG file, and the plain constants `ORCHESTRATOR`, `DATAPRODUCT`,
`READS` and `OUTPUTS`, which other scripts read with `ast` to find the data products to run first (`--upstream`).
"""

import os
import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from datapatchbay.genheader import generated_header
from datapatchbay.integrations.local.script import (
    ANNOUNCE_HELPER,
    CONNECT_HELPER,
    MAIN_HELPER,
    UPSTREAM_HELPER,
)
from datapatchbay.plugins import (
    AuditTask,
    BuildCall,
    DataProductPlan,
    GeneratedFile,
    GenerationContext,
    RenderKind,
    SqlTask,
    TablePlan,
    UnsupportedCombinationError,
)
from datapatchbay.plugins.codegen import (
    RUN_AUDIT_HELPER,
    check_rows,
    plan_builds,
    python_literal,
    render_build,
    warehouse_audits,
)

_NAME = re.compile(r"[A-Za-z0-9_.-]{1,250}")
_INDENT = "    "
_CONNECTION_PREFIX = "DPB_CONNECTION_"


class LocalOrchestrator:
    """Generate a Python script that builds one data product when it runs."""

    render_kind: RenderKind = "function"

    def generate(self, plan: DataProductPlan, context: GenerationContext) -> Sequence[GeneratedFile]:
        """Return the script of the data product, `<folder>.py`.

        Raises:
            UnsupportedCombinationError: If a name is not usable in a script, a table needs a table of a batch it is
                not in, the tables of a batch have different runtimes, or a plugin cannot render a task.
        """
        return [GeneratedFile(PurePosixPath(f"{plan.folder}.py"), _Script(plan, context).render())]


def connection_variable(connection: str) -> str:
    """Return the name of the environment variable that holds the URL of the connection called `connection`."""
    return _CONNECTION_PREFIX + re.sub(r"[^A-Z0-9]", "_", connection.upper())


class _Script:
    def __init__(self, plan: DataProductPlan, context: GenerationContext) -> None:
        self._plan = plan
        self._context = context
        self._imports: set[str] = {
            "import argparse",
            "import ast",
            "import logging",
            "import subprocess",
            "import sys",
            "from pathlib import Path",
        }
        self._helpers: list[str] = []
        self._variables: set[str] = set()
        self._task_ids: set[str] = set()
        self._connects = False

    def render(self) -> str:
        plan = self._plan
        self._check_name("data product", plan.folder, plan.folder)
        for port in (*plan.reads, *plan.outputs):
            self._check_name("port", port, "output port name")
        if not re.search(r"[A-Za-z0-9]", plan.connection):
            raise UnsupportedCombinationError(
                f"connection '{plan.connection}' has no letter or digit to name a variable"
            )
        steps = self._steps()

        if self._connects:
            self._imports.add("import os")
            self._add_helpers(RUN_AUDIT_HELPER, CONNECT_HELPER)
        relative_dir = Path(os.path.relpath(plan.directory, self._context.output_dir)).as_posix()
        constants = [
            f"ORCHESTRATOR = {python_literal('local')}",
            f"DATAPRODUCT = {python_literal(plan.folder)}",
            f"READS = {_tuple(plan.reads)}",
            f"OUTPUTS = {_tuple(plan.outputs)}",
        ]
        if self._connects:
            constants.append(f"CONNECTION_VARIABLE = {python_literal(connection_variable(plan.connection))}")
        constants.append(
            f"DATAPRODUCT_DIR = (Path(__file__).resolve().parent / {python_literal(relative_dir)}).resolve()"
        )
        run = ["def run():", f'{_INDENT}"""Build the data product once. Stop at the first step that fails."""']
        run.extend(f"{_INDENT}{line}" if line else "" for line in steps)
        parts = [
            generated_header(plan.source.file.path) + self._preamble() + "\n" + _render_imports(self._imports),
            "\n".join(constants),
            "LOG = logging.getLogger(DATAPRODUCT)",
            ANNOUNCE_HELPER,
            *self._helpers,
            "\n".join(run),
            UPSTREAM_HELPER,
            MAIN_HELPER,
            'if __name__ == "__main__":\n' + f"{_INDENT}main()",
        ]
        return "\n\n\n".join(parts) + "\n"

    def _preamble(self) -> str:
        """The schedule comment and the docstring that `--help` shows."""
        lines = []
        schedules = self._plan.source_schedules
        if schedules:
            lines += ["", "# This script does not schedule itself. The source input ports deliver data at:"]
            lines += [f"#   {_one_line(s.cron)}  {_one_line(s.port)}" for s in schedules]
        folder = self._plan.folder
        lines += [
            "",
            f'"""Run the data product {_one_line(folder)} once: its builds and audits, then the warehouse SQL.',
            "",
            f"Run `python {_one_line(folder)}.py`, or add `--upstream` to run the local data products it reads first.",
            '"""',
        ]
        return "\n".join(lines) + "\n"

    def _add_helpers(self, *helpers: str) -> None:
        for helper in helpers:
            if helper not in self._helpers:
                self._helpers.append(helper)

    def _check_name(self, what: str, value: str, where: str) -> None:
        if not _NAME.fullmatch(value):
            raise UnsupportedCombinationError(
                f"{what} '{value}' ({where}) is not a valid name for a local script; "
                "use letters, digits, dashes, dots and underscores"
            )

    def _claim_task_id(self, task_id: str, where: str) -> None:
        self._check_name("task id", task_id, where)
        if task_id in self._task_ids:
            raise UnsupportedCombinationError(f"task id '{task_id}' ({where}) is used twice")
        self._task_ids.add(task_id)

    def _variable(self, stem: str) -> str:
        base = re.sub(r"\W", "_", stem)
        name, count = base, 1
        while name in self._variables:
            count += 1
            name = f"{base}_{count}"
        self._variables.add(name)
        return name

    def _steps(self) -> list[str]:
        """Return the lines of `run()`: the Python tables with their audits, the batches, the warehouse's SQL."""
        plan = self._plan
        builds = plan_builds(plan, self._context)
        warehouse = self._context.warehouse
        lines: list[str] = []
        for table in builds.python_tables:
            lines += self._build(table, builds.calls[table.name])
            for audit in warehouse_audits(self._context, table):
                lines.append(self._step(audit, f"audit of table '{table.name}'"))
        for batch in builds.batches:
            lines += self._build(batch.tables[0], batch.call, task_id=batch.task_id, where=batch.where)
        for sql_task in warehouse.apply_tasks(plan) if warehouse is not None else ():
            lines.append(self._step(sql_task, "warehouse"))
        return lines

    def _build(
        self, table: TablePlan, call: BuildCall, *, task_id: str | None = None, where: str | None = None
    ) -> list[str]:
        task_id = task_id or f"build_{table.name}"
        where = where or f"table '{table.name}'"
        self._claim_task_id(task_id, where)
        variable = self._variable(task_id)
        rendered = render_build(
            self._context,
            self._plan.orchestrator,
            LocalOrchestrator.render_kind,
            table,
            call,
            task_id=task_id,
            where=where,
            variable=variable,
        )
        self._imports.update(rendered.imports)
        self._add_helpers(*rendered.helpers)
        return [*rendered.lines, f"_announce({python_literal(task_id)})", f"{variable}()"]

    def _step(self, task: SqlTask | AuditTask, where: str) -> str:
        self._claim_task_id(task.task_id, where)
        self._connects = True
        if isinstance(task, SqlTask):
            return f"_sql_step({python_literal(task.task_id)}, {python_literal(task.sql)})"
        try:
            checks = python_literal(check_rows(task))
        except ValueError as exc:
            raise UnsupportedCombinationError(f"{where}: {exc}") from exc
        return f"_audit_step({python_literal(task.task_id)}, {checks})"


def _tuple(values: Sequence[str]) -> str:
    """Write names as a Python tuple literal."""
    if not values:
        return "()"
    return "(" + ", ".join(python_literal(value) for value in values) + ("," if len(values) == 1 else "") + ")"


def _one_line(text: str) -> str:
    """Collapse whitespace so that a value cannot end a comment or a docstring line."""
    return " ".join(text.split())


def _render_imports(imports: set[str]) -> str:
    """Write imports in a fixed order: plain imports, then `from` imports merged by module."""
    plain = sorted(line for line in imports if line.startswith("import "))
    names: dict[str, set[str]] = defaultdict(set)
    for line in imports:
        if line.startswith("from "):
            module, _, name = line.removeprefix("from ").partition(" import ")
            names[module].add(name)
    merged = [f"from {module} import {', '.join(sorted(names[module]))}" for module in sorted(names)]
    return "\n".join([*plain, *merged])
