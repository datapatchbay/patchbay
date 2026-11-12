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
- An input port's `from` names an existing output port of another data product.
- A data product that reads an output port is listed in that port's readers as a `product:` entry.
- In the `build` block, `executor` is `python`, `entrypoint` has the form `path.py:function` and the file exists inside the data product folder, `needs` names tables of the same data product, and `needs` contains no cycle.
- `kind` is one of the kinds in the conventions. `domain` is in the domain list when the list is not empty, and is accepted as written when it is empty.
- The data product folder name, its default output port name and its private port name equal what the naming templates produce from `name` and `kind`. Any further port name starts with the data product's derived name. An input port that reads another data product keeps the name of the output port it reads.
- Data product, port, table and column names are snake_case.
- Derived data product names and port names are unique across the repo.
- A naming template that uses an unknown placeholder fails, and the message lists the placeholders available.
- An output port does not promise fresher data than its inputs deliver. This rule arrives with a later release.

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

## `dpb generate`

Generated files are build output of CD and are not committed.

One Airflow 3 DAG per data product
: Each table gets a build task followed by an audit task, and task order follows `needs`. A data product with a source input port runs on that port's schedule. A data product that reads another data product's output port is triggered when that port is updated. The DAG ends with a task that applies the views and grants.

Three runtimes
: `worker` calls the entrypoint on the Airflow worker. `docker` and `kubernetes` run it in a container from an image named in the settings.

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
