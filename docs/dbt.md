# dbt reference

Everything about tables built by dbt in one place: the table file, the files that `dpb generate` writes for dbt, the task that runs dbt, and what `dpb new --from-dbt` imports. For the steps, see [Build a table with dbt](howto/dbt.md) and [Import an existing dbt project](howto/import-dbt.md).

## A table built by dbt

A table is built by dbt when its executor resolves to `dbt`: `executor: dbt` on its data product or higher, or `build: {executor: dbt}` on the table itself.

- It has the same contract as any other table, and needs no `build` block.
- `entrypoint`, `params` and `needs` fail on it, because dbt takes the order from the model's `ref()` calls.
- Its SQL is the dbt model `models/<dbt_model>.sql` in the data product's folder. The name comes from the `dbt_model` naming template in `conventions.names`, by default `{dataproduct}__{table}`. A missing model file fails.
- A `.py` file anywhere in a `models/` folder fails, because dbt would read it as a dbt Python model.
- A model reads another data product's output port with `source('<port>', '<table>')`. A `ref()` into another data product's models is a read of a private table and fails.

`dpb` expects one dbt project for the repo, with its `dbt_project.yml` at the repo root. A repo without a table built by dbt needs no `dbt_project.yml`.

[What `dpb validate` checks](validation.md#tables-built-by-dbt) lists every check on these tables, on the committed dbt files and on what the models read.

## Generated dbt files

For tables built by dbt, `dpb generate` writes dbt files into the data product folders, not into the output folder. They are committed, because dbt reads them on every run ([ADR-0013](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0013-dbt-properties-are-generated-from-the-table-file.md)). Nobody writes them by hand. Each starts with a line saying it is generated from the table file.

| File | For | Holds |
| --- | --- | --- |
| `models/<dbt_model>.yml` | Each table built by dbt | The properties of the model |
| `models/_group.yml` | Each data product with such a table | The dbt group, with the data product's owner |
| `models/_sources.yml` | Each input port that reads another data product's output port | A dbt source named after the port |
| `tests/<dbt_model>__<rule>.sql` | Each table rule | A singular dbt data test |
| `dbt_project.yml` at the repo root | The repo | The `model-paths` and `test-paths` keys |

### Properties

The properties file of a model holds:

- the model's description, and each column with `data_type` and description
- an enforced model contract
- the `alias` (the table name), the `schema` (the data product's private schema) and the `group` (the data product)
- each column rule as a dbt data test: `not_null`, `unique` and `accepted_values`
- `pii: true` in the `meta` of a PII column

Severity `error` is written as `error` and `warning` as `warn`. A rule with severity `none` is left out.

### Singular tests

Each table rule becomes a singular dbt data test, with no dbt package needed ([ADR-0019](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0019-table-rules-become-generated-singular-dbt-tests.md)). The SQL selects the rows that break the rule, so the test passes when it returns none:

| Rule | The test selects |
| --- | --- |
| `primary_key` | Rows with a null in a key column, or a key that occurs more than once |
| `row_count` | One row when the row count is outside `min` and `max` |
| `sql` | The rule's SELECT as written, which names the model with `ref()` |

Further rules of the same name in one table file get a suffix `_2`, `_3`. Severity maps as for column rules, and a rule with severity `none` gets no file.

### Sources

For each input port that reads another data product's output port, `models/_sources.yml` holds a dbt source named after the port. It points at the output port's schema and lists the producer's tables and columns from its table files ([ADR-0018](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0018-a-dbt-model-reads-an-output-port-through-a-generated-source.md)). Only the contract is copied: table names, columns and their descriptions, not quality rules or freshness.

When several data products read one output port, the source is written once, in the first of them built by dbt in name order.

### `dbt_project.yml`

Once any table is built by dbt, `dpb generate` owns the `model-paths` and `test-paths` keys of the `dbt_project.yml` at the repo root, and only those. They are replaced by the `models/` and `tests/` folders of the data products with such a table, so an entry added by hand is lost. The file is committed, so `--output` does not move it. They are written after everything else is generated.

- With a table built by dbt, a missing `dbt_project.yml` fails the run (exit 2) with a message saying it is expected at the repo root, and nothing is written.
- When no table is built by dbt any more, `dpb generate` only removes the entries that point at a data product's `models/` or `tests/` folder, and a key if none is left. The file is then not needed.

### Files that nothing produces any more

A properties, sources or test file that carries the generated header but that nothing produces any more is deleted and listed as removed. A file without the header is never touched.

## The schema name macro

The generated properties put each model in its data product's private schema with `config: {schema: <private port name>}`. By default dbt does not use that name as written: it builds `<target schema>_<custom schema>`. For models to land in the private schema as written, the dbt project must override the `generate_schema_name` macro, for example in `macros/generate_schema_name.sql`:

```jinja
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name | trim if custom_schema_name is not none else target.schema }}
{%- endmacro %}
```

`dpb generate` does not write or check this macro, because it never reads the macros of the dbt project. Without it, tables are created in a schema such as `<target schema>_<private port name>`, and the views and grants, which name the private schema, do not find them.

## dbt on the worker

A data product with tables built by dbt gets one task, `build_dbt`, which runs `dbt build --select path:<its models folder>` on the worker.

- It runs after the data product's Python tables, so the dbt models can read their output, and before the views and grants.
- dbt builds the models and runs their data tests in dependency order. A broken rule with severity `error` fails the task, and `dpb` generates no audit task for these tables.
- `dpb` uses the dbt profile the team already has and manages no connection ([ADR-0001](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0001-dpb-never-connects-to-the-warehouse.md)).
- dbt is run as the `dbt` command of the worker's environment. `dpb` installs nothing.

All tables built by dbt in a data product share this one task. So they must resolve to the same `runtime`, and it must be `worker`. A Python table cannot list a dbt table in `needs`, because the Python tables are built first.

## The `dbt` settings

Three settings, in `datapatchbay.yaml` only:

```yaml
dbt:
  project_dir: .                  # the dbt project on the worker
  profiles_dir: ~/.dbt            # the folder with profiles.yml on the worker
  manifest: target/manifest.json  # the dbt manifest made by `dbt parse`
```

`project_dir`
: Where the dbt project is on the worker. A relative path is relative to the repo root as deployed with the generated files. If the dbt project sits elsewhere on the worker with the layout of the repo, set an absolute path. A relative `project_dir` other than `.` must contain the data product folders.

`profiles_dir`
: The folder with `profiles.yml` on the worker. `~` is the home of the worker's user, and a relative path is relative to the dbt project. Authenticate through the profile, for example with environment variables on the worker.

`manifest`
: Read on the machine that runs `dpb validate`, not on the worker. It is relative to the repo root. Set it if `dbt parse` writes elsewhere, for example with `--target-path`.

The defaults assume that the repo is deployed to the worker with the generated files, that `dbt_project.yml` is at the repo root, and that dbt and the profile are installed for the worker's user.

## What `dpb new --from-dbt` imports

`dpb new --from-dbt <path>` builds a data product from the dbt project below `<path>`, which is read recursively. It asks for the name, kind, domain and owners as usual, and `--no-input` still lists what is missing. The data product gets `executor: dbt`, whatever the repo's executor.

For each model that has a `.sql` file and properties with at least one column, it writes two files.

The model, `models/<dbt_model>.sql`
: Named by the `dbt_model` naming template. The SQL is copied, not moved, so the old project keeps working until you switch over, and `dpb` never deletes your files. `ref('old_name')` calls to other imported models are renamed to the new model names.

The table file, `outputs/<port>/<model>.yaml`
: With the model's description and its columns: `data_type` as `type`, `description`, and `pii` from `meta: {pii: true}`. A column without `data_type` is written as `text` and reported, because dbt would check the contract against it.

Quality rules come from the data tests of each column: `not_null`, `unique` and `accepted_values`, with `severity: warn` as `warning`. This is the reverse of what `dpb generate` writes, so `dpb generate` then reproduces the same tests.

- Both `data_tests:` and the older `tests:` are read, with arguments directly under the test or under `arguments:`, and `severity` directly or under `config:`.
- A rule gets an explicit `severity` only when it differs from the default severity in the settings.
- `primary_key`, `row_count` and `sql` are not imported. They are generated as singular tests, which no property ties to a model, so write them by hand from your singular tests.

### What is not imported

What is not imported is reported on stderr, never dropped silently, and is also in the `--json` lists:

| Report | Covers |
| --- | --- |
| `not imported: <model>.<column> <test>: <reason>` | Data tests with no matching rule (`relationships`, package tests, tests on a whole model). Tests with an option that changes what they check (`where`, `limit`, `warn_if`, `error_if`, `store_failures`, a templated severity). `accepted_values` that hold SQL |
| `skipped <model>: <reason>` | Models without properties or columns, properties without a `.sql` file, and properties files that are not readable YAML |
| `no data_type: <model>.<column> is written as 'text'` | A column without `data_type` |
| `ref not renamed: <model> ref(...)` | A `ref` with a package or a version (`ref('pkg', 'model')`, `ref('model', v=2)`), and a `ref` to a model that is not imported. They are copied as written, so edit them by hand |

A model name that is not snake_case, two models with the same name, or a `dbt_model` template that gives two models one name fails the command and writes nothing.

Your hand-written properties are never touched. The ones below the new data product's `models/` folder are a duplicate of the generated ones: `dpb validate` points them out and tells you to remove them. Those elsewhere in the old project stay as they are.
