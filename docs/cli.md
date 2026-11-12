# The `dpb` CLI

| Command | What it does |
| --- | --- |
| `dpb new` | Scaffolds a data product folder that follows the conventions, with a stub function per table. Asks questions in a terminal. With `--no-input` it fails instead of asking |
| `dpb validate` | Validates every data product. Meant for CI |
| `dpb list` | Shows all data products with their kind, domain and owners |
| `dpb describe` | Prints one data product with all settings resolved, for humans or agents |
| `dpb config` | Prints the effective settings and where each one comes from |
| `dpb schema` | Prints the JSON Schema of the four kinds of file |
| `dpb generate` | Writes the orchestrator files and the warehouse SQL. Meant for CD |
| `dpb upgrade` | Rewrites files to the current schema version, keeping comments |

`validate`, `list`, `describe` and `config` take `--json`.

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
- `executor`, `runtime`, `image` and `severity` may be set in `datapatchbay.yaml`, `dataproduct.yaml`, `port.yaml` and a table's `build` block. `orchestrator` is only allowed in `datapatchbay.yaml` and `dataproduct.yaml`.
- Every orchestrator, executor, runtime and warehouse named in the settings has a plugin. The message names the data product and, for an executor or runtime, the table, and points at the line where the name is written. A name set at the root or on a data product is reported for each table it applies to.
- In the `build` block, `entrypoint` has the form `path.py:function` and the file exists inside the data product folder, `needs` names tables of the same data product, and `needs` contains no cycle.
- Every derived name matches its naming template, and every name is snake_case. Port names and data product names are unique across the repo. `kind` is a declared kind. `domain` is in the domain list when one is declared. These rules arrive with later releases.

`dpb validate` looks for `datapatchbay.yaml` in the working directory and its parents, and fails with exit code 2 and a message when it finds none. It exits 0 when every file is valid and 1 when there are problems. Each problem is one line, `file:line: message`, on stderr.

With `--json`, stdout holds only this document:

```json
{
  "ok": false,
  "dataproducts_checked": 1,
  "problems": [
    {"file": "dataproducts/sa_ilab_orders/dataproduct.yaml", "line": 5, "message": "unknown key 'ownr'; ..."}
  ]
}
```

A missing `schema_version`, or one newer than the installed `dpb` knows, is reported as such.

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
sa_ilab_orders  (dataproducts/sa_ilab_orders/dataproduct.yaml)
  settings:
    executor: python  (defaults)
    runtime: docker  (root, datapatchbay.yaml)
    orchestrator: prefect  (dataproduct, dataproducts/sa_ilab_orders/dataproduct.yaml)
```

With `--json`, stdout holds one object with the same content. Its keys are `folder`, `name`, `file`, `kind`, `domain`, `owner`, `technical_owner`, `description`, `settings`, `inputs` and `outputs`. Each port has `name`, `file`, `settings` and `tables`, plus `from` or `kind`; output ports add `freshness`, `readers`, `pii_readers` and `read_by`. Each table has `name`, `file`, `description`, `freshness_column`, `columns`, `rules`, `entrypoint`, `params`, `needs` and `settings`. Each setting is `{"value", "level", "file"}`, where `level` is `table`, `port`, `dataproduct`, `root`, `defaults` or `unset`. Each rule carries its own fields, its resolved `severity` and `severity_from`, which is `rule` when the rule sets the severity itself and otherwise the level the default came from. An unknown name fails with exit code 2 and a message naming the data products that exist.

## `dpb generate`

Generated files are build output of CD and are not committed.

`dpb generate` validates the repo first, exactly like `dpb validate`. When anything is wrong it prints the problems on stderr, writes nothing and exits 1. Otherwise it writes one file per data product into the folder of the `output_dir` setting (`generated` by default, relative to the repo root) and lists the files. `--output <folder>` (`-o`) writes into another folder, relative to the working directory. Files from an earlier run that no longer have a data product are not removed. A failure while generating, such as a table name Airflow cannot use as an id, exits 2 with a message that names the data product, and nothing is written.

```sh
dpb generate
dpb generate --output build/dags
```

The same input gives byte-identical files. The orchestrator, executor, runtime and warehouse are plugins named in the settings (see [Settings and plugins](settings.md)); this release ships the Airflow orchestrator, the Python executor, the `worker` runtime and a Postgres warehouse that does not write any SQL yet.

One Airflow 3 DAG per data product
: The file is named after the data product folder, and so is the DAG. Each table gets a build task followed by an audit task, and task order follows `needs`. A data product with a source input port runs on that port's schedule; all its source input ports must share one schedule. A data product that reads another data product's output port is triggered when that port is updated; with both, it runs on the schedule once the ports are updated. Each output port is an Airflow asset named after the port, and the DAG ends with a `publish_outputs` task that marks the output ports as updated when the DAG succeeds. Between the last table and that task come the tasks that apply the views and grants. (The build tasks exist now; the audit and apply tasks arrive with the Postgres warehouse.)

Three runtimes
: `worker` calls the entrypoint on the Airflow worker: the task loads the entrypoint file from the data product folder and calls the function with the table's `params`. It finds the folder from the DAG file's own location, so the output folder and the data product folders must keep their relative places when deployed; deploying the whole repo as the DAG bundle does that. The `params` must be plain YAML values: a date has to be quoted. `docker` and `kubernetes` run it in a container from an image named in the settings.

No connection management
: The views, grants and audits run on the orchestrator, through a connection that already exists there. The settings only name it. Build code connects by itself.

Views and grants for Postgres
: The executor builds every output table in the data product's private schema. An output port holds only generated views over those tables. A PII column shows its value to PII readers and NULL to everyone else, and readers are granted access to the views. The statements can be re-applied on every run, and removing a reader removes that reader's access.

Audit tasks
: Each quality rule becomes SQL that runs through the orchestrator's connection. A broken rule with severity `error` fails the run, `warning` reports and continues, and `none` is skipped.

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

- `--json` output on `validate`, `list`, `describe` and `config`.
- `dpb describe` prints a data product with every setting resolved, which is everything an agent needs in one call.
- `dpb schema` publishes the JSON Schema, so an agent can validate a file before writing it.
- `--no-input` makes `dpb new` fail instead of prompting.
