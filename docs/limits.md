# Limits and guarantees

What you can rely on when you run datapatchbay in production, and what it does not do. Read this page before you adopt it.

## Guarantees

- **`dpb` never connects.** It reads YAML and writes files. It holds no credentials and ships no database driver. The orchestrator and the build code do all the connecting ([ADR-0001](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0001-dpb-never-connects-to-the-warehouse.md)).
- **Generated files stand alone.** They do not import datapatchbay, so the orchestrator does not need it installed, and the files keep running when datapatchbay is removed.
- **The same input gives byte-identical files.** A deploy without changes changes nothing.
- **Validation reports everything at once.** `dpb validate` lists every problem as `file:line: message` and writes nothing.
- **Generation is all-or-nothing.** `dpb generate` validates first and generates every data product in memory. When anything is wrong, it writes nothing.
- **`dpb` does not overwrite your work.** `dpb new` fails when the folder exists. `dpb generate` writes into the output folder, and for dbt into the data product folders, where it deletes only files that carry its generated header.
- **The files are versioned.** Every file carries `schema_version`, unknown keys fail, and `dpb upgrade` rewrites files after a breaking change. A change to a packaged default counts as breaking.

## Access

- **Postgres is the only warehouse that enforces access.** DuckDB has no roles and no grants. On DuckDB, readers and PII readers are accepted and applied to nothing, and a PII column shows NULL to everyone. DuckDB is meant for local development and tests ([ADR-0021](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0021-duckdb-enforces-no-access.md)).
- **The roles must exist.** The generated SQL grants to roles and never creates them. When a role is missing, the `apply_access` task fails and names it, and the views and grants of the previous run stay in place ([ADR-0017](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0017-warehouse-roles-are-expected-to-exist.md)).
- **The file is the only source of access.** Every run revokes all privileges on the schema of an output port and grants them again from `port.yaml`. A privilege that someone gave by hand is removed.
- **A change takes effect on the next run** of the data product, not when the pull request is merged.
- **The views are dropped and created again on every run.** A view in another schema that selects from a port's view blocks the run until it is removed.
- **The private schema is private only if the logins are separate.** No reader is granted access to a private schema. Whether the build code of one data product can read the private schema of another depends on the login it connects with. Give the build code of each data product its own login, a member of the data product's role.

## What `dpb validate` cannot see

`dpb validate` checks what the files state. It never looks at data or at Python code.

- **Freshness is not measured.** The check compares the promised duration with the cron schedule of the sources and with the freshness of the ports that are read. Nothing checks how old the data in the warehouse really is. `freshness_column` names the column that holds the time of the newest data. Today it is only checked to be a column of the table, and shown by `dpb describe`. Live freshness is on the [roadmap](roadmap.md).
- **Python build code is not read.** For dbt, `dpb validate` checks in the dbt manifest that a model reads other data products only through their output ports. A Python function gets no such check, so for Python the grants in the warehouse are the only enforcement ([ADR-0014](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0014-validate-checks-what-build-code-actually-reads.md)).
- **A table name written straight into SQL is invisible,** in a dbt model as well.
- **The dbt manifest may be stale.** `dpb` does not run dbt. Run `dbt parse` before `dpb validate`.
- **Column types and owners are free text.** A type is written as the warehouse spells it and is not checked. An owner is a name, with no registry behind it.
- **A table built by Python is not compared with its table file.** The view of an output port selects the columns that the table file lists. A column that the build code did not write fails `apply_access`, and a column that the table file does not list stays in the private schema. A table built by dbt has an enforced dbt model contract instead.

## Quality rules

- **Rules run after the build.** The table is already built when its rules run, so readers can see the new data through the output port's view when a rule with severity `error` fails. The run fails, and the data products that read the port are not triggered. Write-audit-publish is on the [roadmap](roadmap.md) ([ADR-0010](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0010-quality-rules-run-as-generated-audit-tasks.md)).
- **A table built by dbt runs its rules as dbt data tests,** during `dbt build`, and gets no audit task.

## Combinations that do not work

- **Containers need Airflow.** The `docker` and `kubernetes` runtimes work with the Airflow orchestrator only. Dagster and the local script run build code in their own process.
- **dbt runs on the worker.** A table built by dbt cannot use a container runtime.
- **Python tables are built before dbt tables.** A Python table cannot list a dbt table in `needs`.
- **One schedule per data product on Airflow.** All source input ports of a data product must share one schedule. Dagster accepts several.
- **Airflow waits for all, Dagster for any.** A data product that reads several output ports runs on Airflow once all of them were updated, and on Dagster when any of them is. See [Run on Dagster](howto/dagster.md#5-schedules-and-sensors).
- **A data product reads only output ports of the same repo.**

## Housekeeping

- **`dpb generate` does not clean the output folder.** The file of a data product that no longer exists stays there, and `dpb validate` fails on it. Remove the output folder before you generate in CD.
- **Writing is not atomic across files.** Each file is written whole or not at all. When a write fails halfway through a run, such as on a full disk, the files already written stay.
- **Once a table is built by dbt, `dpb generate` owns two keys of `dbt_project.yml`:** `model-paths` and `test-paths`. An entry added by hand is lost.

## Not stable yet

- datapatchbay is not released. Install it from GitHub and pin a commit ([Validate in CI](howto/ci.md#use-the-same-version-everywhere)).
- The plugin interface may change. See [Writing a plugin](plugins.md).

The [roadmap](roadmap.md) lists what is planned and what is out of scope.
