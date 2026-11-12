# Writing a plugin

A plugin adds support for one technology: an orchestrator, an executor, a runtime or a warehouse. This page shows the four extension points, how to register a plugin, and the two toolkits that the built-in plugins are written with. The plugin interface and both toolkits are public, but not yet stable in milestone 1: names may change.

## The four extension points

Each extension point is a `Protocol` in `datapatchbay.plugins`. A plugin is any object that has the same methods.

| Extension point | Entry-point group | What it does |
| --- | --- | --- |
| `Orchestrator` | `datapatchbay.orchestrators` | `generate(plan, context)` returns the files for one data product. It composes the DAG from what the other three contribute, and `render_kind` (`task` or `function`) says what build code it needs. |
| `Executor` | `datapatchbay.executors` | `call(table)` says what has to be called to build a table. |
| `Runtime` | `datapatchbay.runtimes` | `call_types` lists the types of call it can run, `render_kinds` lists the kinds of build code it can render, and `render_build_task(task, kind=, variable=)` renders the build task, the place where the code runs. |
| `Warehouse` | `datapatchbay.warehouses` | `apply_tasks(dataproduct)` and `audit_tasks(table)` return the SQL that the orchestrator runs. It never connects to the warehouse. |

The plan data that plugins receive (`DataProductPlan`, `TablePlan`, `GenerationContext`) and the tasks they return (`SqlTask`, `AuditTask`, `BuildTask`, `RenderedTask`, `GeneratedFile`, ...) are in `datapatchbay.plugins` too. A plugin imports only from `datapatchbay.plugins`, and the built-in integrations follow the same rule: no integration imports another integration's folder.

## Register a plugin

A plugin package registers a class, or a function without arguments that returns the plugin, in the entry-point group of its extension point. The entry point name is the name used in the settings:

```toml
[project.entry-points."datapatchbay.warehouses"]
mywarehouse = "my_package.warehouse:MyWarehouse"
```

After `uv add my-package`, the `warehouse: mywarehouse` setting selects it. Plugins are selected by what they can do, never by name in the core. See [Settings and plugins](settings.md#plugins).

## Executor capabilities

An executor can do more than say what to call. The core asks for each extra with `isinstance` on the executor plugin and never asks which executor it is, so an executor has exactly the capabilities it implements. Each is a `runtime_checkable` `Protocol` in `datapatchbay.plugins`, and each is optional. The built-in `dbt` executor implements all of them; `python` implements `ChecksTables` and `ScaffoldsTables`.

| Capability | Method or attribute | Contract |
| --- | --- | --- |
| `WritesCommittedFiles` | `committed_output(planned)` | The executor produces files that are committed in the repo. It returns a `CommittedOutput`: `problems()` diffs it with the disk (`dpb validate`), `write()` writes the files and deletes the `orphans` (`dpb generate`), and `error` says why it cannot be written, which stops `dpb generate` before any write. The core asks every installed executor with this capability, used or not, because files can be left from an earlier run. |
| `ChecksDataProducts` | `check_dataproduct(repo, dataproduct)` | Stage 1 problems with the files of a data product, whichever executor its tables use. Called for every data product, before the checks of its tables. |
| `ChecksTables` | `check_table(settings, dataproduct, table)` | Stage 1 problems with the table files that this executor builds. The plugin object lives for one validation, so it may remember what it saw, such as the names used so far. |
| `ChecksPlans` | `check_plans(planned)` | Stage 2 problems that need the planned repo and the disk, such as comparing what a model reads with the input ports. Never runs when stage 1 found problems. |
| `BatchesBuilds` | `batch_key`, `call_type`, `call(table)` | The tables of a data product that share a `batch_key` are built in one task, `build_<key>`, after the tables that are built one by one. `call(table)` is called with the first of them and returns the one call. No other table can `needs` a table of a batch, the tables of a batch share one runtime, and that runtime must list `call_type` in its `call_types`. |
| `OwnsQualityRules` | `owns_quality_rules(table)` | The executor runs the quality rules of this table itself, so the warehouse gets no audit task for it. |
| `ScaffoldsTables` | `scaffold_table(table)` | For `dpb new`: given a `NewTable`, returns a `ScaffoldedTable` with the `build` block of the table file (or `None`) and the files for the data product folder, such as the stub of the build code. |

## The SQL toolkit: `datapatchbay.plugins.sql`

For warehouse plugins.

`Dialect`
: The parts of the SQL that depend on the warehouse: `identifier` quotes a schema, table or column name, and `literal` writes a value.

`standard_identifier`, `standard_literal`
: Quoting the standard way, which Postgres and DuckDB both read. Use them as the parts of a `Dialect`, or write your own.

`audit_checks(table, dialect)`, `audit_tasks(table, dialect)`
: The quality rules of a table as `AuditCheck` values, one query per rule that counts the rows that break it, and as the one `AuditTask` that holds them. They use only SQL that most warehouses run.

`output_ports(plan)`, `view_sql(table, dialect, pii_column)`
: The output ports of a data product with their tables, and the statement that creates the view of a table in its port's schema. `pii_column` turns the quoted name of a PII column into the expression that the view selects for it.

## The codegen toolkit: `datapatchbay.plugins.codegen`

For orchestrator and runtime plugins that write Python files. A generated file never imports datapatchbay (ADR-0001), so everything here returns source text.

`plan_builds(plan, context)`, `TableBuilds`, `Batch`
: Asks each table's executor how to build it, and returns the tables in build order, split into the tables built one by one and the `Batch` of each executor that builds together. It refuses the combinations that cannot run.

`warehouse_audits(context, table)`
: The audit tasks of the warehouse for a table, none when the table's executor owns its quality rules.

`render_build(context, orchestrator, table, call, task_id=, where=, variable=)`
: Has the table's runtime render its build, and turns a refusal into an `UnsupportedCombinationError` that names the table.

`render_audit_task(audit, connection=, variable=)`, `check_rows`, `AUDIT_HELPER`, `RUN_AUDIT_HELPER`
: The generated code that runs the quality rules of a table. `RUN_AUDIT_HELPER` does not depend on the orchestrator.

`python_literal(value)`
: Writes a plain YAML value as a Python literal, the same way every time.

## A minimal warehouse

This warehouse quotes names with backticks, writes the views of the output ports and audits the quality rules. It imports only `datapatchbay.plugins`:

```python
from collections.abc import Sequence

from datapatchbay.plugins import AuditTask, DataProductPlan, SqlTask, TablePlan
from datapatchbay.plugins.sql import Dialect, audit_tasks, output_ports, view_sql

DIALECT = Dialect(
    identifier=lambda name: "`" + name.replace("`", "``") + "`",
    literal=lambda value: repr(value),
)


class MyWarehouse:
    """Produce SQL for a warehouse that quotes names with backticks."""

    def apply_tasks(self, dataproduct: DataProductPlan) -> Sequence[SqlTask]:
        statements = [
            view_sql(table, DIALECT, pii_column=lambda name: f"NULL AS {name}")
            for _port, tables in output_ports(dataproduct)
            for table in tables
        ]
        return (SqlTask("apply_access", "\n".join(statements)),) if statements else ()

    def audit_tasks(self, table: TablePlan) -> Sequence[SqlTask | AuditTask]:
        return audit_tasks(table, DIALECT)
```

Register it as shown above, then `dpb generate` puts its tasks into the DAG like those of the built-in warehouses.
