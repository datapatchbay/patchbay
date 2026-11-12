# Build a table with dbt

A table is built by a Python function unless its executor is `dbt`. With dbt, the table file still holds the contract, the SQL is a dbt model in the data product folder, and `dpb generate` writes the dbt properties, sources and tests from the files.

This guide builds the table `turnaround` of the data product `agg_order_turnaround` with dbt. The data product has an input port on the output port `sa_jaffle_orders`.

## 1. Choose dbt

Set the executor for the whole data product, in its `dataproduct.yaml`:

```yaml
executor: dbt
```

To build only one table with dbt, set it in that table's file instead:

```yaml
build:
  executor: dbt
```

When `executor: dbt` is set in `datapatchbay.yaml`, `dpb new` scaffolds a stub model per table instead of a Python function.

## 2. Write the contract

The table file has the same contract as any other table, and no `entrypoint`, `params` or `needs`. dbt takes the order of the models from their `ref()` calls.

```yaml
# dataproducts/agg_order_turnaround/outputs/agg_order_turnaround/turnaround.yaml
schema_version: 1
name: turnaround
description: Hours between the order and its completion, one row per completed order
columns:
  - name: order_id
    type: text
    rules: [not_null, unique]
  - name: turnaround_hours
    type: numeric
    rules: [not_null]
rules:
  - rule: row_count
    min: 1
```

## 3. Write the model

The model is `models/<data product>__<table>.sql` in the data product folder. The name comes from the `dbt_model` naming template.

```sql+jinja
-- dataproducts/agg_order_turnaround/models/agg_order_turnaround__turnaround.sql
select
    order_id,
    extract(epoch from completed_at - ordered_at) / 3600 as turnaround_hours
from {{ source('sa_jaffle_orders', 'orders') }}
where completed_at is not null
```

A model reads another data product's output port with `source('<port>', '<table>')`. `dpb generate` writes that dbt source for each input port that reads an output port, so the data product must declare the input port first. Do not use `ref()` on another data product's models: that reads its private tables, and `dpb validate` fails on it.

## 4. Add a dbt project

`dpb` expects a `dbt_project.yml` at the repo root. If the repo has none, create one:

```yaml
name: jaffle_shop
version: "1.0"
profile: jaffle_shop
```

For models to land in the private schema of their data product, the project must also override the `generate_schema_name` macro. See the [table file reference](../files.md#table-file) for the macro.

## 5. Generate the dbt files

```console
$ dpb generate
```

Besides the DAG files, this writes inside the repo:

- `models/agg_order_turnaround__turnaround.yml`: the model's description, columns and types, an enforced model contract, and the column rules as dbt data tests.
- `models/_group.yml`: the dbt group of the data product, with its owner.
- `models/_sources.yml`: a dbt source for each output port that the data product reads, with the tables and columns of that port.
- `tests/agg_order_turnaround__turnaround__row_count.sql`: one singular dbt data test per table rule. It selects the rows that break the rule.
- The `model-paths` and `test-paths` keys of `dbt_project.yml`, with the `models/` and `tests/` folders of every data product that has a table built by dbt.

Commit all of them. dbt reads them on every run. Never edit them by hand: change the table file and run `dpb generate` again.

## 6. Parse and validate

`dpb validate` checks what the dbt models read. It does not run dbt: it reads the dbt manifest that `dbt parse` writes, `target/manifest.json` by default. So run `dbt parse` first, and again after every change to a model:

```console
$ dbt parse
$ dpb validate
ok: 2 data product(s) valid
```

`dbt parse` needs the dbt adapter and a profile, but it does not connect to the warehouse. If it writes the manifest somewhere else, set `dbt.manifest` in `datapatchbay.yaml`. Without a manifest, `dpb validate` fails and says to run `dbt parse`.

The order matters in a new repo: `dpb generate` first, because dbt cannot parse the project without the generated sources, then `dbt parse`, then `dpb validate`.

From now on `dpb validate` fails when a committed dbt file does not match the table file:

```text
dataproducts/agg_order_turnaround/models/agg_order_turnaround__turnaround.yml: dbt properties file does not match its table file; run `dpb generate` to refresh it
```

When you remove a table rule or a table, run `dpb generate` again. It removes the generated files that nothing produces any more and lists them as removed. It never touches a file that you wrote by hand.

## What runs

All dbt tables of a data product share one task in its DAG, `build_dbt`. It runs `dbt build` on the data product's `models/` folder on the Airflow worker, after the Python tables and before the views and grants. dbt runs the data tests itself, so these tables get no audit task. The worker needs the `dbt` command and a profile. See [dbt on the worker](../settings.md#dbt-on-the-worker).

## Limits

- The runtime of a dbt table must be `worker`. `docker` and `kubernetes` fail in `dpb validate`.
- A Python table cannot list a dbt table in `needs`, because the Python tables are built first.
- A `.py` file in a `models/` folder fails, because dbt would read it as a dbt Python model.
- A model that a table file builds must not be declared in another YAML file of a `models/` folder.
