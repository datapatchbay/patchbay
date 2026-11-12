# The `dpb` CLI

| Command | What it does |
| --- | --- |
| `dpb new` | Scaffolds a data product folder that follows the conventions, with a stub function per table (a stub dbt model per table when the executor is `dbt`), or with `--from-dbt` from an existing dbt project's models and properties. Asks questions in a terminal. With `--no-input` it fails instead of asking |
| `dpb validate` | Validates every data product. Meant for CI |
| `dpb list` | Shows all data products with their kind, domain and owners |
| `dpb describe` | Prints one data product with all settings resolved, for humans or agents |
| `dpb config` | Prints the effective settings and where each one comes from |
| `dpb schema` | Prints the JSON Schema of the four kinds of file |
| `dpb generate` | Writes the orchestrator files and the warehouse SQL. Meant for CD |
| `dpb upgrade` | Rewrites files to the current schema version, keeping comments |

`new`, `validate`, `list`, `describe`, `config` and `generate` take `--json`.

## Exit codes

Every command uses the same exit codes, so a script or CI job can act on them:

| Exit code | Meaning |
| --- | --- |
| 0 | The command did what it was asked |
| 1 | The files have problems. `dpb` reports all of them, as `file:line: message` on stderr, and writes nothing |
| 2 | The command could not run: a wrong option, no `datapatchbay.yaml` in the working directory or its parents, an unknown data product, or a failure while generating |

[Troubleshooting](troubleshooting.md) lists the messages and what to do about each.

## `dpb new`

`dpb new` creates `dataproducts/<folder>/` with a `dataproduct.yaml`, the default output port with its `port.yaml` and one example table, and a stub Python function per table that the table's `build` block points at. When the effective executor in `datapatchbay.yaml` is `dbt`, it writes `models/<dbt_model>.sql` per table instead (named by the `dbt_model` naming template) and tables without a `build` block; the example table reads the ingested table with `ref()`. With the Python executor the result passes `dpb validate` without edits; with dbt it does after `dpb generate` has written the properties and `dbt_project.yml`. The folder and port names come from the naming templates in the effective settings. It never overwrites: if the folder exists, it fails and writes nothing.

```sh
dpb new                                                     # asks for what is missing
dpb new --name jaffle_orders --kind source-aligned --domain sales \
  --owner "Jane Doe" --technical-owner "Joe Dev" --no-input
dpb new --name jaffle_orders --kind source-aligned --owner "Jane Doe" --source jaffle_shop --schedule "0 5 * * *"
```

| Flag | Meaning |
| --- | --- |
| `--name`, `--kind`, `--domain`, `--owner`, `--technical-owner` | The answers. Each one given as a flag is not asked. `domain` and `technical-owner` can be left empty, except that `domain` is required when the conventions declare domains |
| `--source` | Also creates the private input port, fed by this source, with a schedule and one ingested table. The example table `needs` it |
| `--schedule` | Cron expression of the source's deliveries. Default `0 5 * * *`. Only used with `--source` |
| `--from-dbt` | A folder with the models (`.sql`) and properties (`.yml`) of an existing dbt project. See below. Cannot be combined with `--source` |
| `--no-input` | Never prompts. Fails with exit code 2 and lists the missing values |
| `--json` | Prints `{"created": [...]}` on stdout: the files it created, relative to the repo root. With `--from-dbt` it also has `unmapped_tests`, `skipped`, `untyped_columns` and `unrewritten_refs` |

### Importing a dbt project with `--from-dbt`

`dpb new --from-dbt <path>` asks for the name, kind, domain and owners as usual (`--no-input` still lists what is missing) and builds the data product from the dbt project below `<path>`, which is read recursively. The data product gets `executor: dbt`, whatever the repo's executor. For each model that has a `.sql` file and properties with at least one column it writes:

- `models/<dbt_model>.sql` in the data product, named by the `dbt_model` naming template. The SQL is **copied**, not moved, so the old project keeps working until you switch over and `dpb` never deletes your files. Delete the originals when you are done, or dbt finds two models. `ref('old_name')` calls to other imported models are renamed to the new model names.
- `outputs/<port>/<model>.yaml`, a table file with the model's description and its columns with `data_type` as `type`, `description`, and `pii` from `meta: {pii: true}`. A column without `data_type` is written as `text` and reported, because dbt would check the contract against it.
- Quality rules from the data tests of each column: `not_null`, `unique` and `accepted_values`, with `severity: warn` as `warning`. This is the reverse of what `dpb generate` writes, so `dpb generate` then reproduces the same tests. Both `data_tests:` and the older `tests:` are read, arguments directly under the test or under `arguments:`, and `severity` directly or under `config:`. A rule gets an explicit `severity` only when it differs from the default severity in the settings. `primary_key`, `row_count` and `sql` are not imported: ADR-0019 generates them as singular tests in `tests/`, which are not tied to a model by a property, so write them by hand from your singular tests.

What is not imported is reported, never dropped silently: as `not imported: <model>.<column> <test>: <reason>` lines, or in the `--json` lists. This covers data tests with no matching rule (`relationships`, package tests, tests on a whole model), tests with an option that changes what they check (`where`, `limit`, `warn_if`, `error_if`, `store_failures`, a templated severity) and `accepted_values` that hold SQL. Models without properties or columns, and properties without a `.sql` file, are listed as `skipped`, and so are properties files that are not readable YAML. The reports go to stderr. The SQL is copied with `ref('model')` renamed to the new model names; a `ref` with a package or a version (`ref('pkg', 'model')`, `ref('model', v=2)`) and a `ref` to a model that is not imported are copied as written and reported as `ref not renamed:`, so edit them by hand. A model name that is not snake_case, two models with the same name, or a `dbt_model` template that gives two models one name fails the command and writes nothing.

Your hand-written properties are never touched. The ones below the new data product's `models/` folder are a duplicate of the generated ones: `dpb validate` points them out and tells you to remove them. Those elsewhere in the old project stay as they are. Run `dpb generate` afterwards to write the dbt properties and the `dbt_project.yml` paths.

## `dpb validate`

`dpb validate` checks every data product and enforces these rules:

- Every file matches the schema, and unknown keys fail. Errors name the file and line, and all errors are reported at once.
- The port lists in `dataproduct.yaml` match the folders under `inputs/` and `outputs/`, in both directions.
- Every `port.yaml` is one of three forms: an output port, an input port fed by a source, or an input port that reads another data product's output port. A key that belongs to another form fails, and the message says which form it belongs to.
- A port of kind `table` has exactly one table file. An input port that reads another data product has none.
- `freshness` is optional on an output port. When given, it is a duration such as `30m`, `24h` or `7d`. `schedule` is a five-field cron expression.
- Every table file matches the schema: columns, `pii`, quality rules on columns (`not_null`, `unique`, `accepted_values`) and on the table (`primary_key`, `row_count`, `sql`), in short or long form, with severity `error`, `warning` or `none`. An unknown rule name fails.
- Table names are unique within a data product.
- An output port with `freshness` does not promise fresher data than its inputs deliver: its freshness is not shorter than the longest gap in the `schedule` of any source input port of the same data product, nor than the `freshness` of any output port the data product reads. The message names both ports and both values. An output port without `freshness` is not checked. The longest gap is computed from the cron expression alone, and `dpb` never looks at data.
- `freshness_column` names a column of its table.
- An input port's `from` names an existing output port of another data product.
- A data product that reads an output port is listed in that port's readers as a `product:` entry.
- `kind` is one of the kinds in the conventions. `domain` is in the domain list when the list is not empty, and is accepted as written when it is empty.
- The data product folder name, its default output port name and its private port name equal what the naming templates produce from `name` and `kind`. Any further port name is the data product's derived name or starts with it and an underscore (`sa_jaffle_orders_extra`, not `sa_jaffle_orders2`). An input port that reads another data product keeps the name of the output port it reads.
- Data product, port, table and column names are snake_case.
- Derived data product names and port names are unique across the repo.
- A naming template that uses an unknown placeholder fails, and the message lists the placeholders available.
- A table built by dbt (its executor resolves to `dbt`) has no `entrypoint`, `params` or `needs`, has its model file `models/<dbt_model>.sql` in the data product's folder, and no `.py` file sits in a `models/` folder. The model name rendered from the `dbt_model` template is a plain identifier (letters, digits and underscores) and is unique across the repo, whatever its case, because dbt model names are unique in a dbt project. Any other table has a `build.entrypoint`.
- The committed dbt files match the table files: `dpb validate` computes the dbt properties and sources files, the singular test files of the table rules and the `model-paths` and `test-paths` of `dbt_project.yml` in memory, as `dpb generate` would write them, and fails on any difference, naming the file and saying to run `dpb generate`. A model that a table file builds must not be declared again in any other YAML file of the `models/` folders. It fails as a duplicate and names both files. A file that carries the generated header but that no table or table rule produces any more fails and says to delete it. This covers the YAML files of every data product's `models/` folder and the SQL files of its `tests/` folder, including the folders of a data product that dbt builds no table of any more, which have dropped out of `model-paths` and `test-paths`. Hand-written files there are left alone. After the last table built by dbt is gone, the `model-paths` and `test-paths` entries that point at data product `models/` and `tests/` folders fail the same way. `dpb validate` writes nothing.
- What `dpb generate` would refuse is found without writing: `dpb validate` generates every data product in memory, once everything else is valid. A table named `dbt` next to tables built by dbt (both would be the task `build_dbt`), a name that is not a valid Airflow id, source input ports with different schedules in one data product and any other refusal of a plugin are reported as a problem on the `dataproduct.yaml`.
- The output folder (the `output_dir` setting) holds no generated file whose data product is gone. A file there that starts with the generated header and names a `dataproduct.yaml` that does not exist fails and says to delete it. `dpb generate` does not delete these files, because the folder is build output that other tools may share. Hand-written files are not looked at, and a folder given with `dpb generate --output` is not known to `dpb validate`.
- `executor`, `runtime`, `image`, `container` and `severity` may be set in `datapatchbay.yaml`, `dataproduct.yaml`, `port.yaml` and a table's `build` block. `orchestrator` is only allowed in `datapatchbay.yaml` and `dataproduct.yaml`.
- Every orchestrator, executor, runtime and warehouse named in the settings has a plugin. The message names the data product and, for an executor or runtime, the table, and points at the line where the name is written. A name set at the root or on a data product is reported for each table it applies to.
- In the `build` block, `entrypoint` has the form `path.py:function` and the file exists inside the data product folder, `needs` names tables of the same data product, and `needs` contains no cycle.

`dpb validate` looks for `datapatchbay.yaml` in the working directory and its parents, and fails with exit code 2 and a message when it finds none. It exits 0 when every file is valid and 1 when there are problems. Each problem is one line, `file:line: message`, on stderr.

With `--json`, stdout holds only this document:

```json
{
  "ok": false,
  "dataproducts_checked": 1,
  "problems": [
    {"file": "dataproducts/sa_jaffle_orders/dataproduct.yaml", "line": 5, "message": "unknown key 'ownr'; ..."}
  ]
}
```

A missing `schema_version`, or one newer than the installed `dpb` knows, is reported as such.

For tables built by dbt, `dpb validate` already checks that the model file exists (see the executor settings), and what the dbt models read:

- A dbt model reads another data product only through the generated `source('<port>', '<table>')` of an input port that it has ([ADR-0014](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0014-validate-checks-what-build-code-actually-reads.md), [ADR-0018](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0018-a-dbt-model-reads-an-output-port-through-a-generated-source.md)). `dpb validate` checks this against the dbt manifest, so CI runs `dbt parse` before `dpb validate`. The manifest is the JSON file at `dbt.manifest` in `datapatchbay.yaml`, by default `target/manifest.json` relative to the repo root. When the repo has tables built by dbt and the file is missing or is not a dbt manifest, validation fails on that file and says to run `dbt parse`. dpb does not run dbt and does not check that the manifest is fresh, so run `dbt parse` after every change to a model. It reads only the standard library `json` and only these fields: `metadata.project_name`, and per node `resource_type`, `name`, `package_name`, `original_file_path` and `depends_on.nodes`, and per source `source_name`, `name` and `schema`; other fields are ignored. A model belongs to the data product whose folder holds its file.
  - A `ref()` to a model in another data product's folder fails as a read of its private schema, naming both models.
  - A `source()` of another data product's output port, with no input port on it in the reading data product, fails and names the port. So does a `source()` that points at the private schema of another data product.
  - Each problem points at the model file and, when the `ref()` or `source()` call can be found in it, at its line. A `source()` of a name that is not an output port of the repo is not a read of a data product and is not checked, and a table name written straight into the SQL is invisible to the check ([ADR-0014](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0014-validate-checks-what-build-code-actually-reads.md)).

`dpb validate` can only test what the files state. Anything that needs real data, such as quality rules, runs as a generated task.

## `dpb config`

`dpb config` prints the effective settings: the packaged defaults with `datapatchbay.yaml` merged over them. Each line holds a setting, its value and where the value comes from, `(defaults)` or `(datapatchbay.yaml)`. Maps are listed leaf by leaf, with dotted names such as `conventions.kinds.aggregate.prefix`.

```text
warehouse                            postgres        (defaults)
runtime                              docker          (datapatchbay.yaml)
conventions.domains                  []              (defaults)
```

With `--json`, stdout holds one object from setting name to `{"value": ..., "origin": "defaults" | "datapatchbay.yaml"}`. An invalid `datapatchbay.yaml` is reported as `file:line: message` and exits with code 2.

## `dpb list`

`dpb list` prints every data product with its kind, domain, owner and technical owner, one per line. With `--json`, stdout holds an array of objects with `folder`, `name`, `kind`, `domain`, `owner` and `technical_owner`. Files that fail validation are left out, and a warning on stderr points to `dpb validate`.

## `dpb describe`

`dpb describe <data product>` takes the folder name or the `name` of a data product. It prints the data product with its ports, tables, columns, quality rules, freshness and readers. For each output port it also shows which data products read it (`read by`). Every setting is resolved and shown with the level it came from, for example `runtime: kubernetes  (port, dataproducts/.../port.yaml)`; a quality rule shows its severity and whether the rule or a level set it.

```text
sa_jaffle_orders  (dataproducts/sa_jaffle_orders/dataproduct.yaml)
  settings:
    executor: python  (defaults)
    runtime: docker  (root, datapatchbay.yaml)
    orchestrator: prefect  (dataproduct, dataproducts/sa_jaffle_orders/dataproduct.yaml)
```

With `--json`, stdout holds one object with the same content. Its keys are `folder`, `name`, `file`, `kind`, `domain`, `owner`, `technical_owner`, `description`, `settings`, `inputs` and `outputs`. Each port has `name`, `file`, `settings` and `tables`, plus `from` or `kind`; output ports add `freshness`, `readers`, `pii_readers` and `read_by`. Each table has `name`, `file`, `description`, `freshness_column`, `columns`, `rules`, `entrypoint`, `params`, `needs` and `settings`. Each setting is `{"value", "level", "file"}`, where `level` is `table`, `port`, `dataproduct`, `root`, `defaults` or `unset`. Each rule carries its own fields, its resolved `severity` and `severity_from`, which is `rule` when the rule sets the severity itself and otherwise the level the default came from. An unknown name fails with exit code 2 and a message naming the data products that exist.

## `dpb generate`

Generated files are build output of CD and are not committed, with one exception: the dbt properties, sources and singular tests and the `model-paths` and `test-paths` of `dbt_project.yml` are committed, because dbt reads them on every run.

`dpb generate` validates the repo first, exactly like `dpb validate`. When anything is wrong it prints the problems on stderr, writes nothing and exits 1. Otherwise it writes one file per data product into the folder of the `output_dir` setting (`generated` by default, relative to the repo root) and lists the files, including the committed dbt files it wrote into the repo and the ones it removed. `--json` prints `{"output_dir", "files", "committed", "removed"}` on stdout instead: `files` are relative to the output folder, the other two relative to the repo root. `--output <folder>` (`-o`) writes into another folder, relative to the working directory. Files in the output folder from an earlier run that no longer have a data product are not removed; `dpb validate` reports them. A failure while generating, such as a table name Airflow cannot use as an id, exits 2 with a message that names the data product, and nothing is written. `dpb validate` finds these failures too.

Generation is all-or-nothing, the writing is not. Every file is written to a temporary file next to it and moved into place, so a file is never half written. A failure while writing (a full disk, a missing permission) exits 2 with a message naming the file, and the files already moved into place stay. The order limits the damage: the output folder first, then the dbt properties, then the deletions, and `dbt_project.yml` last.

The tables of a data product built by dbt share one task, `build_dbt`, that runs `dbt build` on the worker (see [Settings and plugins](settings.md#dbt-on-the-worker)).

When a table is built by dbt, `dpb generate` also updates the `model-paths` and `test-paths` keys of the `dbt_project.yml` at the repo root, and only those. This file is committed, so `--output` does not move it. Once any table is built by dbt, `dpb generate` owns both keys: they are replaced by the `models/` and `tests/` folders of the data products with such a table, so an entry added by hand is lost. When no table is built by dbt any more, it only removes the entries that point at a data product's `models/` or `tests/` folder (and a key if none is left), and the file is not needed. A repo without such a table needs no `dbt_project.yml`; with one, a missing `dbt_project.yml` fails the run (exit 2) with a message saying it is expected at the repo root, and nothing is written.

```sh
dpb generate
dpb generate --output build/dags
```

The same input gives byte-identical files. The orchestrator, executor, runtime and warehouse are plugins named in the settings (see [Settings and plugins](settings.md)); this release ships the Airflow orchestrator, the Python executor, the `worker`, `docker` and `kubernetes` runtimes and two warehouses: Postgres, which writes the SQL for audits, views, masking and grants, and DuckDB, which writes the audits and the views of output ports (no masking by role and no grants, since DuckDB has no roles). With either warehouse the DAG ends with an `apply_access` task, and a data product without output ports gets none.

dbt properties
: For each table built by dbt, `dpb generate` writes `models/<dbt_model>.yml` next to the model, in the data product folder and not in the output folder: the file is committed ([ADR-0013](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0013-dbt-properties-are-generated-from-the-table-file.md)). It starts with a line saying it is generated from the table file. It holds the model's description, each column with `data_type` and description, an enforced model contract, the `alias` (the table name), the `schema` (the data product's private schema) and the `group` (the data product). Each column rule becomes a dbt data test: `not_null`, `unique` and `accepted_values`, with severity `error` as `error` and `warning` as `warn`; a rule with severity `none` is left out. A PII column carries `pii: true` in its `meta`. Each data product with such a table also gets `models/_group.yml`, the dbt group with the data product's owner. Each table rule becomes a singular dbt data test ([ADR-0019](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0019-table-rules-become-generated-singular-dbt-tests.md)): `<dbt_model>__<rule>.sql` in the `tests/` folder of the data product, committed, with no dbt package needed. The SQL selects the rows that break the rule, so the test passes when it returns none: `primary_key` selects rows with a null in a key column or a key that occurs more than once, `row_count` selects one row when the row count is outside `min` and `max`, and `sql` is the rule's SELECT as written, which names the model with `ref()`. Further rules of the same name in one table file get a suffix `_2`, `_3`. Severity maps as for column rules: `error` as `error`, `warning` as `warn`, and a rule with severity `none` gets no file. For each input port that reads another data product's output port, `models/_sources.yml` holds a dbt source named after the port, with the output port's schema and the producer's tables and columns, with descriptions only and no rules ([ADR-0018](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0018-a-dbt-model-reads-an-output-port-through-a-generated-source.md)). When several data products read one output port, the source is written once, in the first of them built by dbt in name order. `dpb generate` also keeps the `test-paths` of `dbt_project.yml` in step with the data product folders, as it does `model-paths`. They are written after everything is generated. A properties or sources file that carries the generated header but that nothing produces any more is deleted and listed as removed; a file without the header is never touched.

One Airflow 3 DAG per data product
: The file is named after the data product folder, and so is the DAG. Each table gets a build task, followed by an audit task when it has quality rules that are not `none`; task order follows `needs`, and a table that needs another waits for that table's audit. A data product with a source input port runs on that port's schedule; all its source input ports must share one schedule. A data product that reads another data product's output port is triggered when that port is updated; with both, it runs on the schedule once the ports are updated. Each output port is an Airflow asset named after the port, and the DAG ends with a `publish_outputs` task that marks the output ports as updated when the DAG succeeds. Between the last table and that task comes the `apply_access` task, which applies the views and grants.

Three runtimes
: `worker` calls the entrypoint on the Airflow worker: the task loads the entrypoint file from the data product folder and calls the function with the table's `params`. It finds the folder from the DAG file's own location, so the output folder and the data product folders must keep their relative places when deployed; deploying the whole repo as the DAG bundle does that. The `params` must be plain YAML values: a date has to be quoted. `docker` and `kubernetes` run it in a container from the table's resolved `image`, as a `DockerOperator` or `KubernetesPodOperator`; DAG files that use them need `apache-airflow-providers-docker` or `apache-airflow-providers-cncf-kubernetes` on Airflow. The container runs `python -c` with a short loader, the entrypoint file, the function and the `params` as JSON, so the image needs `python`, the build code, and the data product folder as its working directory ([ADR-0016](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0016-containers-get-the-entrypoint-as-arguments-to-python.md)). Tables with different runtimes can sit in one DAG. The `container` setting is added to the task as written, which is where a team supplies environment variables or secrets; dpb passes no credentials.

No connection management
: The views, grants and audits run on the orchestrator, through a connection that already exists there. The settings only name it. Build code connects by itself.

Views and grants for Postgres
: The executor builds every output table in the data product's private schema. An output port holds only generated views over those tables. A PII column shows its value to PII readers and NULL to everyone else, and readers are granted access to the views. The statements can be re-applied on every run, and removing a reader removes that reader's access. The roles must already exist in the warehouse; the SQL grants to them and never creates them ([ADR-0017](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0017-warehouse-roles-are-expected-to-exist.md)). The views are dropped and created again on every run, so a view in another schema that depends on an output port's view blocks the apply.

Access on DuckDB
: On DuckDB the warehouse enforces no access: it has no roles and no grants, so readers and PII readers are accepted and applied to nothing, and a PII column always shows NULL in the view, to everyone. DuckDB is meant for local development and tests. The same files work on both warehouses, so a team can develop on DuckDB and deploy on Postgres by changing one setting ([ADR-0021](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0021-duckdb-enforces-no-access.md)).

Audit tasks
: Each quality rule becomes SQL that runs through the orchestrator's connection. A broken rule with severity `error` fails the run, `warning` reports and continues, and `none` is skipped. For a table built by dbt, the rules run as dbt data tests during the dbt build instead. The audit task of a table runs every rule as a query that counts the rows that break it, through the orchestrator's connection, and the audit code is part of the generated file. When a rule with severity `error` is broken the task fails, and its message names the rule, the table and the column; all broken `error` rules are named together. A broken `warning` rule is written to the task log and the task succeeds. A bare rule name takes the default severity, which cascades from `datapatchbay.yaml` down to the table. A table whose rules all have severity `none` gets no audit task. Tables are audited in their data product's private schema. `accepted_values` compares values with the column's type, so write numbers and booleans unquoted for numeric and boolean columns. A `sql` rule's SELECT may end in a semicolon.

dbt properties
: For each table built by dbt, a properties file next to the model with its description, columns and types, quality rules as dbt data tests (table rules as generated singular tests), an enforced dbt model contract, its alias and schema, and its data product's dbt group, plus a dbt source for each output port the data product reads. `dpb generate` also keeps the `model-paths` and `test-paths` of the root `dbt_project.yml` in step with the data product folders.

The generated DAG files do not import datapatchbay, so the orchestrator needs neither datapatchbay nor its dependencies installed.

## `dpb upgrade`

Each schema version bump comes with a migration. `dpb upgrade` rewrites a team's files to the current version and keeps their comments and key order. It ships from the first release, before there is a migration to run, so the first breaking change doesn't also have to invent the way out.

`dpb` refuses files with a `schema_version` newer than it knows.

`dpb upgrade` covers all four kinds of file: `datapatchbay.yaml`, every `dataproduct.yaml`, every `port.yaml` and every table file. A migration is one step from version n to n+1, and the steps run in order until a file is current. Version 1 is the only version, so for now the command reports that there is nothing to do and exits 0.

```sh
dpb upgrade             # rewrite files that are behind
dpb upgrade --dry-run   # show what would change as a diff and write nothing
```

If any file cannot be upgraded, because its `schema_version` is newer than `dpb` knows, is missing or has no migration, `dpb upgrade` prints a problem for it, writes nothing and exits 1.

## Built for agents

- `--json` output on `new`, `validate`, `list`, `describe`, `config` and `generate`.
- `dpb describe` prints a data product with every setting resolved, which is everything an agent needs in one call.
- `dpb schema` publishes the JSON Schema, so an agent can validate a file before writing it.
- `--no-input` makes `dpb new` fail instead of prompting.
