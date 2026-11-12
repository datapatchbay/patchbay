# The `dpb` CLI

| Command | What it does |
| --- | --- |
| [`dpb new`](#dpb-new) | Scaffolds a data product folder that follows the conventions |
| [`dpb validate`](#dpb-validate) | Validates every data product. Meant for CI |
| [`dpb list`](#dpb-list) | Shows all data products with their kind, domain and owners |
| [`dpb describe`](#dpb-describe) | Prints one data product with all settings resolved, for humans or agents |
| [`dpb config`](#dpb-config) | Prints the effective settings and where each one comes from |
| [`dpb schema`](#dpb-schema) | Prints the JSON Schema of the four kinds of file |
| [`dpb generate`](#dpb-generate) | Writes the orchestrator files and the warehouse SQL. Meant for CD |
| [`dpb upgrade`](#dpb-upgrade) | Rewrites files to the current schema version, keeping comments |

A command that reads the repo looks for `datapatchbay.yaml` in the working directory and its parents, so it runs from anywhere inside the repo.

`new`, `validate`, `list`, `describe`, `config` and `generate` take `--json` and then print one JSON document on stdout. With `dpb describe --json`, `dpb schema` and `dpb new --no-input`, an agent can read a data product in one call, check a file before it writes it, and never meet a prompt.

## Exit codes

Every command uses the same exit codes, so a script or CI job can act on them:

| Exit code | Meaning |
| --- | --- |
| 0 | The command did what it was asked |
| 1 | The files have problems. `dpb` reports all of them, as `file:line: message` on stderr, and writes nothing |
| 2 | The command could not run: a wrong option, no `datapatchbay.yaml` in the working directory or its parents, an unknown data product, or a failure while writing a file (a full disk, a permission) or while syncing `dbt_project.yml` (it is missing or unusable) |

[Troubleshooting](troubleshooting.md) lists the messages and what to do about each.

## `dpb new`

`dpb new` creates `dataproducts/<folder>/` with:

- a `dataproduct.yaml`
- the default output port, with its `port.yaml` and one example table
- a stub Python function per table, which the table's `build` block points at

The folder and port names come from the naming templates in the effective settings. The result passes `dpb validate` without edits. `dpb new` never overwrites: if the folder exists, it fails and writes nothing. In a terminal it asks for each value that is not given as a flag.

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
| `--from-dbt` | A folder with the models (`.sql`) and properties (`.yml`) of an existing dbt project. Cannot be combined with `--source` |
| `--no-input` | Never prompts. Fails with exit code 2 and lists the missing values |
| `--json` | Prints `{"created": [...]}` on stdout: the files it created, relative to the repo root. With `--from-dbt` it also has `unmapped_tests`, `skipped`, `untyped_columns` and `unrewritten_refs` |

With the dbt executor
: When the effective executor in `datapatchbay.yaml` is `dbt`, `dpb new` writes a stub model `models/<dbt_model>.sql` per table instead of a Python function, named by the `dbt_model` naming template, and table files without a `build` block. The example table reads the ingested table with `ref()`. The result passes `dpb validate` after `dpb generate` has written the dbt properties and `dbt_project.yml`.

With `--from-dbt`
: `dpb new --from-dbt <path>` builds the data product from the models of an existing dbt project. [Import an existing dbt project](howto/import-dbt.md) shows the steps, and the [dbt reference](dbt.md#what-dpb-new---from-dbt-imports) lists what is imported and what is not.

## `dpb validate`

`dpb validate` checks every data product: each file against the schema, and the rules across files, such as names, readers and freshness. [What `dpb validate` checks](validation.md) lists every rule.

It exits 0 when every file is valid and 1 when there are problems. Each problem is one line, `file:line: message`, on stderr, and all problems are reported at once. `dpb validate` writes nothing.

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

A repo with tables built by dbt runs `dbt parse` first, because `dpb validate` reads the dbt manifest. See [Validate in CI](howto/ci.md#repos-with-dbt).

## `dpb list`

`dpb list` prints every data product with its kind, domain, owner and technical owner, one per line. With `--json`, stdout holds an array of objects with `folder`, `name`, `kind`, `domain`, `owner` and `technical_owner`. Files that fail validation are left out, and a warning on stderr points to `dpb validate`.

## `dpb describe`

`dpb describe <data product>` takes the folder name or the `name` of a data product. It prints the data product with its ports, tables, columns, quality rules, freshness and readers. For each output port it also shows which data products read it (`read by`).

Every setting is resolved and shown with the level it came from. A quality rule shows its severity and whether the rule or a level set it.

```text
sa_jaffle_orders  (dataproducts/sa_jaffle_orders/dataproduct.yaml)
  settings:
    executor: python  (defaults)
    runtime: docker  (root, datapatchbay.yaml)
    orchestrator: dagster  (dataproduct, dataproducts/sa_jaffle_orders/dataproduct.yaml)
```

An unknown name fails with exit code 2 and a message naming the data products that exist.

With `--json`, stdout holds one object with the same content:

| Object | Keys |
| --- | --- |
| The data product | `folder`, `name`, `file`, `kind`, `domain`, `owner`, `technical_owner`, `description`, `settings`, `inputs` and `outputs` |
| A port | `name`, `file`, `settings` and `tables`, plus `from` or `kind`. An output port adds `freshness`, `readers`, `pii_readers` and `read_by` |
| A table | `name`, `file`, `description`, `freshness_column`, `columns`, `rules`, `entrypoint`, `params`, `needs` and `settings` |
| A setting | `value`, `level` and `file`, where `level` is `table`, `port`, `dataproduct`, `root`, `defaults` or `unset` |
| A rule | Its own fields, its resolved `severity`, and `severity_from`: `rule` when the rule sets the severity itself, and otherwise the level the default came from |

## `dpb config`

`dpb config` prints the effective settings: the packaged defaults with `datapatchbay.yaml` merged over them. Each line holds a setting, its value and where the value comes from, `(defaults)` or `(datapatchbay.yaml)`. Maps are listed leaf by leaf, with dotted names such as `conventions.kinds.aggregate.prefix`.

```text
warehouse                            postgres        (defaults)
runtime                              docker          (datapatchbay.yaml)
conventions.domains                  []              (defaults)
```

With `--json`, stdout holds one object from setting name to `{"value": ..., "origin": "defaults" | "datapatchbay.yaml"}`. An invalid `datapatchbay.yaml` is reported as `file:line: message` and exits with code 2.

## `dpb schema`

`dpb schema` prints the JSON Schema of the four kinds of file, so an editor or an agent can check a file before writing it.

```sh
dpb schema root         # datapatchbay.yaml
dpb schema dataproduct  # dataproduct.yaml
dpb schema port         # port.yaml, in its three forms
dpb schema table        # a table file
dpb schema              # all four, as one JSON object keyed by kind
```

The schema is generated from the same models `dpb validate` uses. It accepts the short form of a column rule, a bare `not_null` or `unique`. The schema checks the shape of a file. The cross-file checks of `dpb validate` (names, folders, readers, freshness) are not in it. [Set up your editor](howto/editor.md) shows how to point an editor at the schema.

## `dpb generate`

`dpb generate` writes one file per data product into the output folder: an Airflow DAG, a Dagster module or a local script, as the `orchestrator` setting says. The file holds the build tasks, the audits of the quality rules, and the SQL of the views and grants. [What `dpb generate` writes](generated.md) describes the files.

```sh
dpb generate
dpb generate --output build/dags
```

| Flag | Meaning |
| --- | --- |
| `--output <folder>`, `-o` | Writes into another folder than the `output_dir` setting (`generated` by default, relative to the repo root). The folder is relative to the working directory |
| `--json` | Prints `{"output_dir", "files", "committed", "removed"}` on stdout. `files` are relative to the output folder, the other two relative to the repo root |

Generated files are build output of CD and are not committed, with one exception. For tables built by dbt, `dpb generate` also writes dbt properties, sources and tests into the data product folders and updates two keys of `dbt_project.yml`. Those are committed, because dbt reads them on every run. See the [dbt reference](dbt.md#generated-dbt-files).

It validates first
: `dpb generate` validates the repo, then generates every data product in memory. It does not compare the committed dbt files, the manifest or the output folder, so it needs no dbt manifest. When anything is wrong, including a data product that a plugin refuses to generate, it prints the problems on stderr, writes nothing and exits 1. With `--json` it then prints `{"ok": false, "problems": [{"file", "line", "message"}, ...]}`, the problems in the same shape as in `dpb validate --json`.

It reports what it wrote
: It lists the files in the output folder, the committed dbt files it wrote into the repo, and the ones it removed.

It does not clean the output folder
: Files in the output folder from an earlier run that no longer have a data product are not removed. `dpb validate` reports them.

It writes file by file
: Generation is all-or-nothing, the writing is not. Every file is written to a temporary file next to it and moved into place, so a file is never half written. A failure while writing (a full disk, a missing permission) exits 2 with a message naming the file, and the files already moved into place stay. The order limits the damage: the output folder first, then the dbt properties, then the deletions, and `dbt_project.yml` last.

The same input gives byte-identical files.

## `dpb upgrade`

Each schema version bump comes with a migration. `dpb upgrade` rewrites a team's files to the current version and keeps their comments and key order.

```sh
dpb upgrade             # rewrite files that are behind
dpb upgrade --dry-run   # show what would change as a diff and write nothing
```

It covers all four kinds of file: `datapatchbay.yaml`, every `dataproduct.yaml`, every `port.yaml` and every table file. A migration is one step from version n to n+1, and the steps run in order until a file is current.

Version 1 is the only version, so for now the command reports that there is nothing to do and exits 0. It ships before there is a migration to run, so the first breaking change does not also have to invent the way out.

If any file cannot be upgraded, because its `schema_version` is newer than `dpb` knows, is missing or has no migration, `dpb upgrade` prints a problem for it, writes nothing and exits 1. `dpb` refuses files with a `schema_version` newer than it knows.
