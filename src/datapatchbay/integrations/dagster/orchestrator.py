"""The `dagster` orchestrator: one Python module per data product that defines Dagster definitions (ADR-0023).

The module has an asset for every table and output port, asset checks for the quality rules, a job, schedules and
sensors, and ends with `defs`, which a team merges with the `defs` of its other data products. It defines
`DATAPRODUCT_DIR`, the data product folder found from the file's own location, so a runtime can load the build code
without the working directory. It imports only `dagster` and the standard library (ADR-0001).
"""

import os
import re
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from datapatchbay.files.genheader import generated_header
from datapatchbay.integrations.dagster.helpers import (
    AUDIT_CHECK_HELPER,
    COUNT_HELPER,
    EXECUTE_HELPER,
    READ_SENSOR_HELPER,
    SQL_CHECK_HELPER,
)
from datapatchbay.plugins import (
    AuditTask,
    BuildCall,
    DataProductPlan,
    GeneratedFile,
    GenerationContext,
    PythonCall,
    RenderKind,
    SqlTask,
    TablePlan,
    UnsupportedCombinationError,
)
from datapatchbay.plugins.codegen import Batch, check_rows, plan_builds, python_literal, render_build, warehouse_audits

_NAME = re.compile(r"[A-Za-z0-9_]+")
_INDENT = "    "
_RESERVED = frozenset(
    {"dg", "Path", "importlib", "os", "subprocess", "defs", "job", "schedule", "DATAPRODUCT_DIR"}
    | {"_build_function", "_command_function", "_execute", "_count_violations"}
    | {"_audit_check", "_sql_check", "_read_sensor"}
)
"""Names the module uses itself, so no asset, check or sensor takes them as a Python name."""


class DagsterOrchestrator:
    """Generate a Python module with the Dagster definitions of one data product."""

    render_kind: RenderKind = "function"

    def generate(self, plan: DataProductPlan, context: GenerationContext) -> Sequence[GeneratedFile]:
        """Return the module of the data product.

        The assets of the data product form one group, which one job builds. The job runs on the cron of the source
        input port, one schedule for the crons of all of them, and whenever an output port that the data product
        reads is materialized.

        Raises:
            UnsupportedCombinationError: If a name is not usable in Dagster, a table needs a table of a batch it is
                not in, the tables of a batch have different runtimes, or a plugin cannot render a task.
        """
        return [GeneratedFile(PurePosixPath(f"{plan.folder}.py"), _Module(plan, context).render())]


class _Module:
    def __init__(self, plan: DataProductPlan, context: GenerationContext) -> None:
        self._plan = plan
        self._context = context
        self._imports: set[str] = {"from pathlib import Path"}
        self._helpers: list[str] = []
        self._names: set[str] = set(_RESERVED)
        self._ops: set[str] = set()
        self._builds: list[str] = []  # the build functions, assigned at module level
        self._checks: list[str] = []  # the asset checks, assigned at module level
        self._assets: list[str] = []  # the source of each asset definition
        self._asset_names: list[str] = []
        self._check_names: list[str] = []
        self._keys: dict[str, str] = {}  # table name -> its asset key as a Python expression

    def render(self) -> str:
        plan = self._plan
        self._check_name("data product", plan.folder, "folder name")
        for port in (*plan.reads, *plan.outputs):
            self._check_name("port", port, "asset key")
        self._tables()
        self._output_ports()
        definitions = self._definitions()

        source = plan.source.file.path
        relative_dir = Path(os.path.relpath(plan.directory, self._context.output_dir)).as_posix()
        parts = [
            generated_header(source) + "\n" + self._render_imports(),
            f"DATAPRODUCT_DIR = (Path(__file__).resolve().parent / {python_literal(relative_dir)}).resolve()",
            *self._helpers,
        ]
        for group in (self._builds, self._checks):
            if group:
                parts.append("\n".join(group))
        parts.extend(self._assets)
        parts.append(definitions)
        return "\n\n\n".join(parts) + "\n"

    def _render_imports(self) -> str:
        """Write imports in a fixed order: standard library plain imports, `from` imports, then dagster."""
        plain = sorted(line for line in self._imports if line.startswith("import "))
        names = sorted(line for line in self._imports if line.startswith("from "))
        return "\n".join(plain + names) + "\n\nimport dagster as dg"

    def _check_name(self, what: str, value: str, where: str) -> None:
        if not _NAME.fullmatch(value):
            raise UnsupportedCombinationError(
                f"{what} '{value}' ({where}) is not a valid Dagster name; use letters, digits and underscores"
            )

    def _variable(self, stem: str) -> str:
        base = re.sub(r"\W", "_", stem)
        if base[0].isdigit():
            base = f"_{base}"
        name, count = base, 1
        while name in self._names:
            count += 1
            name = f"{base}_{count}"
        self._names.add(name)
        return name

    def _claim_name(self, name: str, where: str) -> str:
        self._check_name("name", name, where)
        if name in self._ops:
            raise UnsupportedCombinationError(f"Dagster name '{name}' ({where}) is used twice")
        self._ops.add(name)
        return name

    def _helper(self, text: str) -> None:
        if text not in self._helpers:
            self._helpers.append(text)

    def _key(self, table: str) -> str:
        return python_literal([self._plan.folder, table])

    def _asset_key(self, table: str) -> str:
        return f"dg.AssetKey({self._key(table)})"

    def _metadata(self) -> str:
        return f'{{"owner": {python_literal(self._plan.owner)}}}'

    def _resource(self) -> str:
        connection = self._plan.connection
        self._check_name("connection", connection, "resource key")
        return connection

    def _tables(self) -> None:
        """Add the asset of every Python table with its checks, then one asset per batch of tables.

        The tables of a batch share one multi-asset that depends on the Python tables no other table needs,
        because their executor builds them and runs their rules together.
        """
        builds = plan_builds(self._plan, self._context)
        for table in self._plan.tables:
            self._check_name("table", table.name, "asset key")
            self._keys[table.name] = self._key(table.name)
        needed: set[str] = set()
        for table in builds.python_tables:
            call = builds.calls[table.name]
            assert isinstance(call, PythonCall)
            self._python_table(table, call)
            needed.update(table.needs)
        leaves = [table.name for table in builds.python_tables if table.name not in needed]
        for batch in builds.batches:
            self._batch(batch, leaves)

    def _build(self, table: TablePlan, call: BuildCall, *, task_id: str, where: str) -> str:
        """Add the build function that the runtime renders; return its name."""
        variable = self._variable(task_id)
        rendered = render_build(
            self._context,
            self._plan.orchestrator,
            DagsterOrchestrator.render_kind,
            table,
            call,
            task_id=task_id,
            where=where,
            variable=variable,
        )
        self._imports.update(rendered.imports)
        for helper in rendered.helpers:
            self._helper(helper)
        self._builds.extend(rendered.lines)
        return variable

    def _deps(self, tables: Sequence[str], *, reads: bool) -> list[str]:
        keys = [self._asset_key(name) for name in tables]
        if reads:
            keys.extend(f"dg.AssetKey({python_literal([port])})" for port in self._plan.reads)
        return keys

    def _python_table(self, table: TablePlan, call: PythonCall) -> None:
        plan = self._plan
        where = f"table '{table.name}'"
        op = self._claim_name(f"{plan.folder}__{table.name}", where)
        build = self._build(table, call, task_id=f"build_{table.name}", where=where)
        function = self._variable(op)
        arguments = [
            f"key={self._key(table.name)}",
            f"group_name={python_literal(plan.folder)}",
        ]
        deps = self._deps(table.needs, reads=not table.needs)
        if deps:
            arguments.append(_list("deps", deps))
        arguments.append(f"metadata={self._metadata()}")
        self._assets.append(
            "\n".join(
                [
                    *_call("@dg.asset", arguments),
                    f"def {function}():",
                    f"{_INDENT}{build}()",
                    f"{_INDENT}return dg.MaterializeResult()",
                ]
            )
        )
        self._asset_names.append(function)
        self._audits(table)

    def _audits(self, table: TablePlan) -> None:
        used: set[str] = set()
        for audit in warehouse_audits(self._context, table):
            where = f"audit of table '{table.name}'"
            op = self._claim_name(f"{self._plan.folder}__{audit.task_id}", where)
            variable = self._variable(audit.task_id)
            resource = python_literal(self._resource())
            if isinstance(audit, SqlTask):
                arguments = [
                    python_literal(op),
                    python_literal(_unique(audit.task_id, used)),
                    self._key(table.name),
                    resource,
                    python_literal(audit.sql),
                ]
                self._helper(EXECUTE_HELPER)
                self._helper(SQL_CHECK_HELPER)
                self._checks.extend(_call(f"{variable} = _sql_check", arguments))
            else:
                self._audit_check(variable, op, table, audit, used)
            self._check_names.append(variable)

    def _audit_check(self, variable: str, op: str, table: TablePlan, audit: AuditTask, used: set[str]) -> None:
        rows = []
        for row in check_rows(audit):
            name = _unique(f"{row['rule']}_{row['column'] or ''}", used)
            rows.append(f"{_INDENT}{python_literal({'name': name, **row})},")
        arguments = [python_literal(op), self._key(table.name), python_literal(self._resource())]
        arguments.append("\n".join(["[", *rows, "]"]))
        self._helper(COUNT_HELPER)
        self._helper(AUDIT_CHECK_HELPER)
        self._checks.extend(_call(f"{variable} = _audit_check", arguments))

    def _batch(self, batch: Batch, leaves: list[str]) -> None:
        """Add the one multi-asset that builds the tables of a batch, after the Python tables."""
        plan = self._plan
        tables = batch.tables
        op = self._claim_name(f"{plan.folder}__{batch.task_id}", batch.where)
        build = self._build(tables[0], batch.call, task_id=batch.task_id, where=batch.where)
        function = self._variable(op)
        deps = self._deps(leaves, reads=True)
        specs = [self._spec(self._key(t.name), deps) for t in tables]
        arguments = [f"name={python_literal(op)}", _list("specs", specs)]
        lines = [f"def {function}():", f"{_INDENT}{build}()"]
        lines += [f"{_INDENT}yield dg.MaterializeResult(asset_key={self._keys[t.name]})" for t in tables]
        self._assets.append("\n".join([*_call("@dg.multi_asset", arguments), *lines]))
        self._asset_names.append(function)

    def _spec(self, key: str, deps: Sequence[str]) -> str:
        arguments = [key, f"group_name={python_literal(self._plan.folder)}"]
        if deps:
            arguments.append(_list("deps", deps))
        arguments.append(f"metadata={self._metadata()}")
        return "\n".join(_call("dg.AssetSpec", arguments))

    def _output_ports(self) -> None:
        """Add the multi-asset with one asset per output port, which runs the warehouse's SQL for the ports.

        It exists without any SQL too, as the asset that other data products depend on.
        """
        plan = self._plan
        if not plan.outputs:
            return
        warehouse = self._context.warehouse
        sql_tasks = list(warehouse.apply_tasks(plan)) if warehouse is not None else []
        op = self._claim_name(f"{plan.folder}__output_ports", "output ports")
        function = self._variable(op)
        deps = self._deps(list(self._keys), reads=False)
        specs = [self._spec(python_literal([port]), deps) for port in plan.outputs]
        arguments = [f"name={python_literal(op)}", _list("specs", specs)]
        lines = [f"def {function}({'context' if sql_tasks else ''}):"]
        if sql_tasks:
            arguments.append(f"required_resource_keys={{{python_literal(self._resource())}}}")
            self._helper(EXECUTE_HELPER)
            lines.append(
                f"{_INDENT}with getattr(context.resources, {python_literal(plan.connection)}).get_connection()"
                " as connection:"
            )
            for sql_task in sql_tasks:
                lines.append(f"{_INDENT * 2}_execute(connection, {python_literal(sql_task.sql)})")
        lines += [f"{_INDENT}yield dg.MaterializeResult(asset_key={python_literal([port])})" for port in plan.outputs]
        self._assets.append("\n".join([*_call("@dg.multi_asset", arguments), *lines]))
        self._asset_names.append(function)

    def _definitions(self) -> str:
        """Return the job, schedules, sensors and `defs`, which close the module."""
        plan = self._plan
        lines: list[str] = []
        folder = python_literal(plan.folder)
        names: dict[str, list[str]] = {"jobs": [], "schedules": [], "sensors": []}
        if self._asset_names:
            lines += _call(
                "job = dg.define_asset_job",
                [f"name={folder}", f"selection=dg.AssetSelection.groups({folder})"],
            )
            names["jobs"].append("job")
            crons = sorted({schedule.cron for schedule in plan.source_schedules})
            if crons:
                cron = python_literal(crons[0] if len(crons) == 1 else crons)
                schedule_name = self._claim_name(f"{plan.folder}__schedule", "schedule")
                arguments = [
                    f"name={python_literal(schedule_name)}",
                    "job=job",
                    f"cron_schedule={cron}",
                    'execution_timezone="UTC"',
                    "default_status=dg.DefaultScheduleStatus.RUNNING",
                ]
                lines += ["", *_call("schedule = dg.ScheduleDefinition", arguments)]
                names["schedules"].append("schedule")
            for port in plan.reads:
                sensor_name = self._claim_name(f"{plan.folder}__on_{port}", "sensor")
                variable = self._variable(sensor_name)
                self._helper(READ_SENSOR_HELPER)
                call = f"{variable} = _read_sensor({python_literal(sensor_name)}, {python_literal(port)}, job)"
                lines += ["", call]
                names["sensors"].append(variable)
        arguments = []
        if self._asset_names:
            arguments.append(_list("assets", self._asset_names))
        if self._check_names:
            arguments.append(_list("asset_checks", self._check_names))
        for field, values in names.items():
            if values:
                arguments.append(_list(field, values))
        defs = _call("defs = dg.Definitions", arguments) if arguments else ["defs = dg.Definitions()"]
        return "\n".join([*lines, "", *defs]).lstrip("\n")


def _call(head: str, arguments: Sequence[str]) -> list[str]:
    """Write a call with one argument per line."""
    lines = [f"{head}("]
    for argument in arguments:
        first, *rest = argument.split("\n")
        lines.append(f"{_INDENT}{first}")
        lines.extend(f"{_INDENT}{line}" if line else "" for line in rest)
        lines[-1] += ","
    lines.append(")")
    return lines


def _list(name: str, items: Sequence[str]) -> str:
    """Write `name=[...]` with one item per line."""
    lines = [f"{name}=["]
    for item in items:
        lines.extend(f"{_INDENT}{line}" for line in item.split("\n"))
        lines[-1] += ","
    return "\n".join([*lines, "]"])


def _unique(stem: str, used: set[str]) -> str:
    """Return a check name made of `stem`, with characters Dagster does not accept replaced, unused in `used`."""
    base = re.sub(r"[^A-Za-z0-9_]+", "_", stem).strip("_") or "check"
    name, count = base, 1
    while name in used:
        count += 1
        name = f"{base}_{count}"
    used.add(name)
    return name
