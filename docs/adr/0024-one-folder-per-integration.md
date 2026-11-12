# One folder per integration; the core names no technology

The support for one technology lives in one folder, `src/datapatchbay/integrations/<technology>/`: `airflow`, `dagster`, `local`, `postgres`, `duckdb`, `dbt`, `python`, `worker`, `docker` and `kubernetes`. A folder holds everything for that technology, whatever its type: dbt is an executor and also writes properties, sources and tests, and Postgres is a warehouse and also writes the access SQL. What several integrations share is public toolkit code in `datapatchbay.plugins`: `plugins.sql` (audit SQL, port views, quoting) and `plugins.codegen` (table builds, audit code, literals), or sits in `_container` (the container rendering of `docker` and `kubernetes`). An integration imports its own folder, `_container` for `docker` and `kubernetes`, and otherwise only `datapatchbay.plugins`; the same test enforces it. Each integration is still registered through an entry point (ADR-0009), and the entry point names are unchanged.

The core, which is every module outside `integrations/` (grouped by stage into `files/`, `settings/`, `checks/`, `pipeline/` and `commands/`, next to `cli/`, `models/` and `plugins/`), names no technology, selects plugins by what they can do and never by name, and imports no integration. A test (`tests/datapatchbay/test_integration_boundary.py`) enforces the last rule with an explicit allow-list. The allow-list holds the imports of dbt that the core still has; each entry has a reason, and the list only shrinks. A runtime is selected by what the orchestrator needs, not by the orchestrator's name: an orchestrator declares a render kind (`task` for Airflow operators, `function` for a plain Python function that Dagster and `local` call), a runtime declares the kinds it supports, and `Runtime.render_build_task` receives the kind. A kind the runtime does not support gives the same "cannot render tasks for orchestrator" error as before. Documented exceptions stay in the file format: the `dbt:` settings block, the `dbt_model` naming template and `dpb new --from-dbt`.

We chose this so that adding an orchestrator, executor, runtime or warehouse is a change in one folder, and so that the layout of the package shows the architecture: before, dbt was eight top-level modules, Airflow was three files in `builtin/`, and the shared audit-code generator was called `airflow_audit`.

## Considered options

- **Keep `builtin/` and group by type (`orchestrators/`, `executors/`, ...).** Rejected: one technology is then spread over several folders, and dbt, which is an executor with its own output files, has no single place.
- **Separate distributions per integration.** Rejected for now: nothing is released, and the interfaces are not stable (ADR-0009). The folders can be split off later without changing an entry point name.
- **Compatibility modules at the old paths.** Rejected: nothing is released, so nobody imports the old paths.

## Consequences

- Moving a module changes only its path, not its behaviour: the generated files and the output of `validate`, `describe`, `list` and `config` are unchanged.
- The core imports no integration except `dpb new --from-dbt`. What it needs of an executor it gets through capabilities: committed files, checks, batching builds, owning quality rules and scaffolding. A third-party executor gets the same powers by implementing the same protocols.
- An executor asks a runtime to run a `PythonCall` or a `CommandCall` (argv, working directory, environment); the `worker` runtime renders a command call without knowing which tool it is. The `dbt:` settings block resolved into the plan (`DbtLocation`, `TablePlan.dbt`) stays in `datapatchbay.plugins` as plan data, as a documented exception.
- The tests mirror the layout, in `tests/datapatchbay/integrations/<technology>/`.
