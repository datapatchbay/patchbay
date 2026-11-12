# What `dpb validate` checks

`dpb validate` checks every data product and reports every problem at once, as `file:line: message`. It reads files only: it never connects to the warehouse and never looks at data. [The `dpb` CLI](cli.md#dpb-validate) describes the command, its exit codes and its `--json` output, and [Troubleshooting](troubleshooting.md) lists the messages.

## Files and keys

- Every file matches the schema, and unknown keys fail.
- A missing `schema_version`, or one newer than the installed `dpb` knows, is reported as such.
- Every table file matches the schema: columns, `pii`, quality rules on columns (`not_null`, `unique`, `accepted_values`) and on the table (`primary_key`, `row_count`, `sql`), in short or long form, with severity `error`, `warning` or `none`. An unknown rule name fails.
- `freshness_column` names a column of its table.

## Names

- `kind` is one of the kinds in the conventions.
- `domain` is in the domain list when the list is not empty, and is accepted as written when it is empty.
- The data product folder name, its default output port name and its private port name equal what the naming templates produce from `name` and `kind`.
- Any further port name is the data product's derived name, or starts with it and an underscore: `sa_jaffle_orders_extra`, not `sa_jaffle_orders2`.
- An input port that reads another data product keeps the name of the output port it reads.
- Data product, port, table and column names are snake_case.
- Derived data product names and port names are unique across the repo.
- Table names are unique within a data product.
- A naming template that uses an unknown placeholder fails, and the message lists the placeholders available.

## Ports

- The port lists in `dataproduct.yaml` match the folders under `inputs/` and `outputs/`, in both directions.
- Every `port.yaml` is one of three forms: an output port, an input port fed by a source, or an input port that reads another data product's output port. A key that belongs to another form fails, and the message says which form it belongs to.
- A port of kind `table` has exactly one table file. An input port that reads another data product has none.
- An input port's `from` names an existing output port of another data product.
- `schedule` is a five-field cron expression.

## Readers

- A data product that reads an output port is listed in that port's readers as a `product:` entry.
- A `product:` reader names a data product in the repo.

## Freshness

- `freshness` is optional on an output port. When given, it is a duration such as `30m`, `24h` or `7d`.
- An output port with `freshness` does not promise fresher data than its inputs deliver. Its freshness is not shorter than the longest gap in the `schedule` of any source input port of the same data product, nor than the `freshness` of any output port the data product reads. The message names both ports and both values.
- An output port without `freshness` is not checked.

The longest gap is computed from the cron expression alone. `dpb` never looks at data.

## Build and settings

- In the `build` block, `entrypoint` has the form `path.py:function` and the file exists inside the data product folder.
- `needs` names tables of the same data product, and contains no cycle.
- A table that is not built by dbt has a `build.entrypoint`.
- `executor`, `runtime`, `image`, `container` and `severity` may be set in `datapatchbay.yaml`, `dataproduct.yaml`, `port.yaml` and a table's `build` block. `orchestrator` is only allowed in `datapatchbay.yaml` and `dataproduct.yaml`.
- Every orchestrator, executor, runtime and warehouse named in the settings has a plugin. The message names the data product and, for an executor or runtime, the table, and points at the line where the name is written. A name set at the root or on a data product is reported for each table it applies to.
- A table whose `runtime` is `docker` or `kubernetes` has an `image` at some level.

## Tables built by dbt

- A table built by dbt (its executor resolves to `dbt`) has no `entrypoint`, `params` or `needs`.
- Its model file `models/<dbt_model>.sql` exists in the data product's folder.
- No `.py` file sits in a `models/` folder, because dbt would read it as a dbt Python model.
- The model name rendered from the `dbt_model` template is a plain identifier (letters, digits and underscores) and is unique across the repo, whatever its case, because dbt model names are unique in a dbt project.
- All tables built by dbt in a data product resolve to the `worker` runtime. `docker` and `kubernetes` fail at the line of the table's runtime.
- A Python table does not list a dbt table in `needs`, because the Python tables are built first.
- A `dbt_project.yml` exists at the repo root.

### The committed dbt files match the table files

`dpb validate` computes in memory what `dpb generate` would write, and fails on any difference, naming the file and saying to run `dpb generate`. This covers:

- the dbt properties and sources files in every data product's `models/` folder
- the singular test files of the table rules, in its `tests/` folder
- the `model-paths` and `test-paths` of `dbt_project.yml`

Next to that:

- A model that a table file builds is not declared again in any other YAML file of the `models/` folders. It fails as a duplicate and names both files.
- A file that carries the generated header but that no table or table rule produces any more fails, and the message says to delete it. This includes the folders of a data product that dbt builds no table of any more, which have dropped out of `model-paths` and `test-paths`.
- After the last table built by dbt is gone, the `model-paths` and `test-paths` entries that point at data product `models/` and `tests/` folders fail the same way.

Hand-written files in those folders are left alone.

### What the dbt models read

A dbt model reads another data product only through the generated `source('<port>', '<table>')` of an input port that its data product has ([ADR-0014](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0014-validate-checks-what-build-code-actually-reads.md), [ADR-0018](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0018-a-dbt-model-reads-an-output-port-through-a-generated-source.md)). `dpb validate` checks this against the dbt manifest:

- A `ref()` to a model in another data product's folder fails as a read of its private schema, naming both models.
- A `source()` of another data product's output port, with no input port on it in the reading data product, fails and names the port.
- A `source()` that points at the private schema of another data product fails.

Each problem points at the model file and, when the `ref()` or `source()` call can be found in it, at its line. A model belongs to the data product whose folder holds its file.

Two things are not checked. A `source()` of a name that is not an output port of the repo is not a read of a data product. A table name written straight into the SQL is invisible to the check.

The manifest is the JSON file at `dbt.manifest` in `datapatchbay.yaml`, by default `target/manifest.json` relative to the repo root:

- When the repo has tables built by dbt and the file is missing or is not a dbt manifest, validation fails on that file and says to run `dbt parse`.
- `dpb` does not run dbt and does not check that the manifest is fresh. Run `dbt parse` after every change to a model, and in CI before `dpb validate`.
- `dpb` reads the manifest with the standard library `json`, and only these fields: `metadata.project_name`; per node `resource_type`, `name`, `package_name`, `original_file_path` and `depends_on.nodes`; per source `source_name`, `name` and `schema`. Other fields are ignored.

## What `dpb generate` would refuse

Once everything else is valid, `dpb validate` generates every data product in memory, without writing. What `dpb generate` would refuse is reported as a problem on the `dataproduct.yaml`:

- a table named `dbt` next to tables built by dbt, because both would be the task `build_dbt`
- a name that is not a valid Airflow id
- source input ports with different schedules in one data product, on Airflow
- a runtime that the orchestrator does not support, such as `docker` with Dagster
- any other refusal of a plugin

## The output folder

The output folder (the `output_dir` setting) holds no generated file whose data product is gone. A file there that starts with the generated header and names a `dataproduct.yaml` that does not exist fails, and the message says to delete it. `dpb generate` does not delete these files, because the folder is build output that other tools may share.

Hand-written files are not looked at, and a folder given with `dpb generate --output` is not known to `dpb validate`.

## What it cannot check

`dpb validate` can only test what the files state. Anything that needs real data, such as quality rules, runs as a generated task. [Limits and guarantees](limits.md#what-dpb-validate-cannot-see) lists what stays unchecked.
