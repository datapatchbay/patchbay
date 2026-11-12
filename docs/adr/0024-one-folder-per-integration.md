# One folder per integration; the core names no technology

The support for one technology lives in one folder, `src/datapatchbay/integrations/<technology>/`: `airflow`, `dagster`, `local`, `postgres`, `duckdb`, `dbt`, `python`, `worker`, `docker` and `kubernetes`. A folder holds everything for that technology, whatever its type: dbt is an executor and also writes properties, sources and tests, and Postgres is a warehouse and also writes the access SQL. What several integrations share sits in folders that start with an underscore: `_sql` (audit SQL, port views, quoting), `_codegen` (table builds, audit code, literals) and `_container` (the container rendering of `docker` and `kubernetes`). Each integration is still registered through an entry point (ADR-0009), and the entry point names are unchanged.

The core, which is every module outside `integrations/`, names no technology, selects plugins by what they can do and never by name, and imports no integration. A test (`tests/datapatchbay/test_integration_boundary.py`) enforces the last rule with an explicit allow-list. The allow-list holds the imports of dbt that the core still has; each entry has a reason, and the list only shrinks. A runtime is selected by what the orchestrator needs, not by the orchestrator's name: an orchestrator declares a render kind (`task` for Airflow operators, `function` for a plain Python function that Dagster and `local` call), a runtime declares the kinds it supports, and `Runtime.render_build_task` receives the kind. A kind the runtime does not support gives the same "cannot render tasks for orchestrator" error as before. Documented exceptions stay in the file format: the `dbt:` settings block, the `dbt_model` naming template and `dpb new --from-dbt`.

We chose this so that adding an orchestrator, executor, runtime or warehouse is a change in one folder, and so that the layout of the package shows the architecture: before, dbt was eight top-level modules, Airflow was three files in `builtin/`, and the shared audit-code generator was called `airflow_audit`.

## Considered options

- **Keep `builtin/` and group by type (`orchestrators/`, `executors/`, ...).** Rejected: one technology is then spread over several folders, and dbt, which is an executor with its own output files, has no single place.
- **Separate distributions per integration.** Rejected for now: nothing is released, and the interfaces are not stable (ADR-0009). The folders can be split off later without changing an entry point name.
- **Compatibility modules at the old paths.** Rejected: nothing is released, so nobody imports the old paths.

## Consequences

- Moving a module changes only its path, not its behaviour: the generated files and the output of `validate`, `describe`, `list` and `config` are unchanged.
- The imports of dbt that the core still has are removed one by one, by putting dbt behind the executor interface, until only the documented exceptions are left.
- One shared folder still imports an integration: `_sql/audit_sql.py` imports the dbt executor name, so that warehouse audits skip tables dbt owns. The boundary test covers the core only; this import goes with the dbt capability work above.
- The tests mirror the layout, in `tests/datapatchbay/integrations/<technology>/`.
