# Build a table with dbt

A table is built by a Python function unless its executor is `dbt`. With dbt, the table file still holds the contract, the SQL is a dbt model in the data product folder, and `dpb generate` writes the dbt properties from the table file.

This guide builds the table `turnaround` of the data product `agg_lab_turnaround` with dbt.

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

## 2. Write the contract

The table file has the same contract as any other table, and no `entrypoint`, `params` or `needs`. dbt takes the order of the models from their `ref()` calls.

```yaml
# dataproducts/agg_lab_turnaround/outputs/agg_lab_turnaround/turnaround.yaml
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
```

## 3. Write the model

The model is `models/<data product>__<table>.sql` in the data product folder. The name comes from the `dbt_model` naming template.

```sql
-- dataproducts/agg_lab_turnaround/models/agg_lab_turnaround__turnaround.sql
select
    order_id,
    extract(epoch from completed_at - ordered_at) / 3600 as turnaround_hours
from sa_ilab_orders.orders
where completed_at is not null
```

A model reads another data product through the views of its output port, here `sa_ilab_orders.orders`. `dpb` does not generate dbt sources, so how the model names that view is up to your dbt project.

## 4. Add a dbt project

`dpb` expects a `dbt_project.yml` at the repo root. If the repo has none, create one:

```yaml
name: lab
version: "1.0"
profile: lab
```

For models to land in the private schema of their data product, the project must also override the `generate_schema_name` macro. See the [table file reference](../files.md#table-file) for the macro.

## 5. Generate the properties

```console
$ dpb generate
```

Besides the DAG files, this writes three things inside the repo:

- `models/agg_lab_turnaround__turnaround.yml`: the model's description, columns and types, an enforced model contract, and the column rules as dbt data tests.
- `models/_group.yml`: the dbt group of the data product, with its owner.
- The `model-paths` key of `dbt_project.yml`, with the `models/` folder of every data product that has a table built by dbt.

Commit all three. dbt reads them on every run. Never edit them by hand: change the table file and run `dpb generate` again.

## 6. Validate

```console
$ dpb validate
ok: 2 data product(s) valid
```

From now on `dpb validate` fails when the committed properties do not match the table file:

```text
dataproducts/agg_lab_turnaround/models/agg_lab_turnaround__turnaround.yml: dbt properties file does not match its table file; run `dpb generate` to refresh it
```

## What runs

All dbt tables of a data product share one task in its DAG, `build_dbt`. It runs `dbt build` on the data product's `models/` folder on the Airflow worker, after the Python tables and before the views and grants. dbt runs the data tests itself, so these tables get no audit task. The worker needs the `dbt` command and a profile. See [dbt on the worker](../settings.md#dbt-on-the-worker).

## Limits

- A table rule (`primary_key`, `row_count` or `sql`) fails on a dbt table with "not supported for dbt yet". Column rules work.
- The runtime of a dbt table must be `worker`. `docker` and `kubernetes` fail in `dpb validate`.
- A Python table cannot list a dbt table in `needs`, because the Python tables are built first.
- A `.py` file in a `models/` folder fails, because dbt would read it as a dbt Python model.
- A model that a table file builds must not be declared in another YAML file of a `models/` folder.
