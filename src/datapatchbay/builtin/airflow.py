"""The `airflow` orchestrator: one Airflow 3 DAG file per data product, written against `airflow.sdk`.

The file defines `DATAPRODUCT_DIR`, the data product folder found from the file's own location, so a runtime can
load the build code without the working directory. The output folder and the data product folders must keep their
relative places when they are deployed, for example by deploying the repo as the DAG bundle.
"""

import os
import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from datapatchbay.builtin.airflow_audit import render_audit_task
from datapatchbay.genheader import generated_header
from datapatchbay.literals import python_literal
from datapatchbay.plugins import (
    AuditTask,
    BuildTask,
    DataProductPlan,
    DbtCall,
    GeneratedFile,
    GenerationContext,
    PythonCall,
    RenderedTask,
    SqlTask,
    TablePlan,
    UnsupportedCombinationError,
)

_ID = re.compile(r"[A-Za-z0-9_.-]{1,250}")
_INDENT = "    "


class AirflowOrchestrator:
    """Generate an Airflow 3 DAG that builds the tables of one data product."""

    def generate(self, plan: DataProductPlan, context: GenerationContext) -> Sequence[GeneratedFile]:
        """Return the DAG file of the data product.

        The DAG runs on the schedule of the data product's source input port and, when it reads output ports of
        other data products, once those ports are updated. It marks its own output ports as updated when it ends.

        Raises:
            UnsupportedCombinationError: If a name is not usable as an Airflow id, the source input ports have
                different schedules, or a plugin cannot render a task.
        """
        return [GeneratedFile(PurePosixPath(f"{plan.folder}.py"), _DagFile(plan, context).render())]


class _DagFile:
    def __init__(self, plan: DataProductPlan, context: GenerationContext) -> None:
        self._plan = plan
        self._context = context
        self._imports: set[str] = {
            "from airflow.sdk import DAG",
            "from datetime import datetime",
            "from pathlib import Path",
        }
        self._helpers: list[str] = []
        self._body: list[str] = []
        self._variables: set[str] = set()
        self._task_ids: set[str] = set()
        self._needed: set[str] = set()  # tables that a later task follows, so they are not the last

    def render(self) -> str:
        plan = self._plan
        self._check_id("data product", plan.folder, plan.folder)
        schedule = self._schedule()
        done = self._tables()
        self._finish(done)

        source = plan.source.file.path
        relative_dir = Path(os.path.relpath(plan.directory, self._context.output_dir)).as_posix()
        parts = [
            generated_header(source) + "\n" + _render_imports(self._imports),
            f"DATAPRODUCT_DIR = (Path(__file__).resolve().parent / {python_literal(relative_dir)}).resolve()",
        ]
        parts.extend(self._helpers)
        header = [
            "with DAG(",
            f"{_INDENT}dag_id={python_literal(plan.folder)},",
            f"{_INDENT}schedule={schedule},",
            f"{_INDENT}start_date=datetime(2025, 1, 1),",
            f"{_INDENT}catchup=False,",
            f'{_INDENT}default_args={{"owner": {python_literal(plan.owner)}}},',
            f'{_INDENT}tags=["datapatchbay"],',
            "):",
        ]
        body = [f"{_INDENT}{line}" if line else "" for line in self._body] or [f"{_INDENT}pass"]
        parts.append("\n".join([*header, *body]))
        return "\n\n\n".join(parts) + "\n"

    def _check_id(self, what: str, value: str, where: str) -> None:
        if not _ID.fullmatch(value):
            raise UnsupportedCombinationError(
                f"{what} '{value}' ({where}) is not a valid Airflow id; "
                "use letters, digits, dashes, dots and underscores"
            )

    def _variable(self, stem: str) -> str:
        base = re.sub(r"\W", "_", stem)
        name, count = base, 1
        while name in self._variables:
            count += 1
            name = f"{base}_{count}"
        self._variables.add(name)
        return name

    def _claim_task_id(self, task_id: str, where: str) -> None:
        self._check_id("task id", task_id, where)
        if task_id in self._task_ids:
            raise UnsupportedCombinationError(f"task id '{task_id}' ({where}) is used twice")
        self._task_ids.add(task_id)

    def _schedule(self) -> str:
        plan = self._plan
        crons = sorted({schedule.cron for schedule in plan.source_schedules})
        if len(crons) > 1:
            listed = ", ".join(f"'{s.port}' ({s.cron})" for s in plan.source_schedules)
            raise UnsupportedCombinationError(
                f"the source input ports have different schedules: {listed}; an Airflow DAG has one schedule"
            )
        for name in (*plan.reads, *plan.outputs):
            self._check_id("port", name, "asset name")
        assets = "[" + ", ".join(_asset(name) for name in plan.reads) + "]"
        if plan.reads:
            self._imports.add("from airflow.sdk import Asset")
        if crons and plan.reads:
            self._imports.update(
                {"from airflow.sdk import AssetOrTimeSchedule", "from airflow.sdk import CronTriggerTimetable"}
            )
            timetable = f'CronTriggerTimetable({python_literal(crons[0])}, timezone="UTC")'
            return f"AssetOrTimeSchedule(timetable={timetable}, assets={assets})"
        if crons:
            return python_literal(crons[0])
        if plan.reads:
            return assets
        return "None"

    def _tables(self) -> dict[str, list[str]]:
        """Add the build tasks and audit tasks; return the variables that mean 'table done' per table.

        Each Python table has a build task and its audit tasks. The tables built by dbt share one task that runs after
        the Python tables, because dbt runs their models and data tests together.
        """
        context = self._context
        calls = {table.name: context.executors[table.executor].call(table) for table in self._plan.tables}
        dbt_tables = [table for table in self._plan.tables if isinstance(calls[table.name], DbtCall)]
        dbt_names = {table.name for table in dbt_tables}
        done: dict[str, list[str]] = {}
        for table in self._plan.tables:
            if table.name in dbt_names:
                continue
            for need in table.needs:
                if need in dbt_names:
                    raise UnsupportedCombinationError(
                        f"table '{table.name}' needs table '{need}', which dbt builds after the Python tables; "
                        "dbt tables cannot be needed"
                    )
            build = self._build(table, calls[table.name])
            audits = [
                self._audit_task(audit, f"audit of table '{table.name}'") for audit in self._warehouse_audits(table)
            ]
            for audit in audits:
                self._body.append(f"{build} >> {audit}")
            done[table.name] = audits or [build]
            for need in table.needs:
                for upstream in done[need]:
                    self._body.append(f"{upstream} >> {build}")
            self._needed.update(table.needs)
        if dbt_tables:
            self._dbt(dbt_tables, calls, done)
        return done

    def _dbt(self, tables: list[TablePlan], calls: dict[str, PythonCall | DbtCall], done: dict[str, list[str]]) -> None:
        """Add the one task that builds the dbt tables with `dbt build`, after every Python table is done."""
        first = tables[0]
        for table in tables:
            if table.runtime != first.runtime:
                raise UnsupportedCombinationError(
                    f"tables '{first.name}' and '{table.name}' are built by dbt in one task, "
                    f"but their runtimes are '{first.runtime}' and '{table.runtime}'"
                )
        upstream = [variable for name, variables in done.items() if name not in self._needed for variable in variables]
        build = self._build(first, calls[first.name], task_id="build_dbt", where="tables built by dbt")
        self._body.extend(f"{variable} >> {build}" for variable in upstream)
        self._needed.update(done)  # the dbt task follows every Python table, so only it is last
        for table in tables:
            done[table.name] = [build]

    def _build(
        self, table: TablePlan, call: PythonCall | DbtCall, *, task_id: str | None = None, where: str | None = None
    ) -> str:
        task_id = task_id or f"build_{table.name}"
        where = where or f"table '{table.name}'"
        self._claim_task_id(task_id, where)
        runtime = self._context.runtimes[table.runtime]
        variable = self._variable(task_id)
        task = BuildTask(task_id=task_id, table=table, call=call)
        try:
            rendered = runtime.render_build_task(task, orchestrator=self._plan.orchestrator, variable=variable)
        except ValueError as exc:
            raise UnsupportedCombinationError(f"{where}: {exc}") from exc
        self._add(rendered)
        return variable

    def _warehouse_audits(self, table: TablePlan) -> Sequence[SqlTask | AuditTask]:
        warehouse = self._context.warehouse
        return warehouse.audit_tasks(table) if warehouse is not None else ()

    def _add(self, rendered: RenderedTask) -> None:
        self._imports.update(rendered.imports)
        for helper in rendered.helpers:
            if helper not in self._helpers:
                self._helpers.append(helper)
        self._body.extend(rendered.lines)

    def _audit_task(self, audit: SqlTask | AuditTask, where: str) -> str:
        if isinstance(audit, SqlTask):
            return self._sql_task(audit, where)
        self._claim_task_id(audit.task_id, where)
        variable = self._variable(audit.task_id)
        try:
            self._add(render_audit_task(audit, connection=self._plan.connection, variable=variable))
        except ValueError as exc:
            raise UnsupportedCombinationError(f"{where}: {exc}") from exc
        return variable

    def _sql_task(self, sql_task: SqlTask, where: str) -> str:
        self._claim_task_id(sql_task.task_id, where)
        self._imports.add("from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator")
        variable = self._variable(sql_task.task_id)
        self._body.extend(
            [
                f"{variable} = SQLExecuteQueryOperator(",
                f"{_INDENT}task_id={python_literal(sql_task.task_id)},",
                f"{_INDENT}conn_id={python_literal(self._plan.connection)},",
                f"{_INDENT}sql={python_literal(sql_task.sql)},",
                ")",
            ]
        )
        return variable

    def _finish(self, done: dict[str, list[str]]) -> None:
        """After every table: the warehouse's SQL, then the task that marks the output ports as updated."""
        plan = self._plan
        last = list(
            dict.fromkeys(
                variable for table in plan.tables if table.name not in self._needed for variable in done[table.name]
            )
        )
        warehouse = self._context.warehouse
        for sql_task in warehouse.apply_tasks(plan) if warehouse is not None else ():
            variable = self._sql_task(sql_task, "warehouse")
            self._body.extend(f"{upstream} >> {variable}" for upstream in last)
            last = [variable]
        if plan.outputs:
            self._claim_task_id("publish_outputs", "output ports")
            self._imports.add("from airflow.sdk import Asset")
            self._imports.add("from airflow.sdk import task")
            outlets = ", ".join(_asset(name) for name in plan.outputs)
            self._body.extend(
                [
                    "",
                    f'@task(task_id="publish_outputs", outlets=[{outlets}])',
                    "def publish_outputs():",
                    f'{_INDENT}"""Mark the output ports as updated; Airflow does so when this task succeeds."""',
                    "",
                    "publish = publish_outputs()",
                ]
            )
            self._body.extend(f"{upstream} >> publish" for upstream in last)


def _asset(name: str) -> str:
    return f"Asset(name={python_literal(name)}, uri={python_literal(f'x-datapatchbay://{name}')})"


def _render_imports(imports: set[str]) -> str:
    """Write imports in a fixed order: plain imports, then `from` imports merged by module, Airflow last."""
    plain = sorted(line for line in imports if line.startswith("import "))
    names: dict[str, set[str]] = defaultdict(set)
    for line in imports:
        if line.startswith("from "):
            module, _, name = line.removeprefix("from ").partition(" import ")
            names[module].add(name)
    standard = [module for module in sorted(names) if not module.startswith("airflow")]
    third_party = [module for module in sorted(names) if module.startswith("airflow")]

    def render(modules: list[str]) -> list[str]:
        return [f"from {module} import {', '.join(sorted(names[module]))}" for module in modules]

    groups = [[*plain, *render(standard)], render(third_party)]
    return "\n\n".join("\n".join(group) for group in groups if group)
