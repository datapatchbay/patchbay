# File reference

This page covers schema version 1.

## Repository layout

```text
datapatchbay.yaml
dataproducts/
  sa_jaffle_orders/
    dataproduct.yaml
    inputs/
      sa_jaffle_orders_private/
        port.yaml
        ingested_orders.yaml
    outputs/
      sa_jaffle_orders/
        port.yaml
        orders.yaml
    src/
      ingested_orders.py
      orders.py
  agg_order_turnaround/
    dataproduct.yaml
    inputs/
      sa_jaffle_orders/
        port.yaml
    outputs/
      agg_order_turnaround/
        port.yaml
        turnaround.yaml
    models/
      agg_order_turnaround__turnaround.sql
      agg_order_turnaround__turnaround.yml   # generated, committed
dbt_project.yml                              # only when a table is built by dbt
```

There are four kinds of file:

- `datapatchbay.yaml` at the root
- per data product, one `dataproduct.yaml`
- one `port.yaml` per port
- one YAML file per table

The build code of a data product lives in its folder: Python modules in `src/`, dbt models in `models/`. A team chooses Python or dbt per data product, or per table.

Every file carries `schema_version`, and unknown keys fail validation. Every file also accepts a free-form `meta` map for a team's own extras.

## `datapatchbay.yaml`

This file holds the settings that apply to all data products. Defaults ship inside the package, so it only needs the values you change, and it can be one line long. The example below shows every setting:

```yaml
schema_version: 1
warehouse: postgres       # postgres | duckdb (duckdb: no roles, no grants)
orchestrator: airflow
executor: python
runtime: worker            # worker | docker | kubernetes
severity: error            # default severity of quality rules
connection: warehouse      # the orchestrator's connection to the warehouse
output_dir: generated      # where `dpb generate` writes, relative to the repo root
dbt:                       # declared by the dbt plugin (see "Settings that a plugin declares" in settings.md)
  project_dir: .           # the dbt project on the worker; relative to the repo root as deployed with the DAG files
  profiles_dir: ~/.dbt     # the folder with profiles.yml on the worker
  manifest: target/manifest.json  # made by `dbt parse`; `dpb validate` reads it, relative to the repo root
conventions:
  kinds:
    source-aligned: {prefix: sa}
    aggregate: {prefix: agg}
    consumer-aligned: {prefix: ca}
  domains: []              # empty means any domain is accepted
  names:
    dataproduct: "{kind.prefix}_{name}"
    output_port: "{kind.prefix}_{name}"
    private_port: "{kind.prefix}_{name}_private"
    role: "dp_{kind.prefix}_{name}"
    dbt_model: "{dataproduct}__{table}"   # declared by the dbt plugin
```

A naming template may use `{name}` (the data product's bare name), `{kind.prefix}` and `{kind.name}`. The `dbt_model` template also has `{dataproduct}` (the data product's derived name) and `{table}`, because dbt model names must be unique across a dbt project. `dpb validate` compares the folder name, the default output port name and the private port name with what the templates produce, so changing a prefix or a template changes what it expects.

The `dbt:` block and the `dbt_model` template are declared by the `dbt` plugin, not by datapatchbay itself: a root section named after an installed plugin is valid only if that plugin declares it, and `dpb validate` fails on any other with "no installed plugin declares a settings section". See [Settings](settings.md) for how these values merge with the defaults and with settings lower down.

## `dataproduct.yaml`

```yaml
schema_version: 1
name: jaffle_orders
kind: source-aligned
domain: operations
owner: Jane Doe
technical_owner: John Roe
description: Jaffle shop orders as received from the shop's order system
inputs: [sa_jaffle_orders_private]
outputs: [sa_jaffle_orders]
```

- `name` is written without the kind's prefix. Naming templates produce the folder name, the port names and the role name.
- `owner` and `technical_owner` are people, written as free text and not validated.
- `kind` must be one of the kinds in the conventions. It is a label, and it does not restrict what a data product may read. See [Three kinds of data product](data-products.md#three-kinds-of-data-product).
- `domain` is free text, unless `conventions.domains` lists the domains.
- `inputs` and `outputs` list port names and must match the folders.

## `port.yaml`

An output port:

```yaml
schema_version: 1
kind: schema               # schema | table
freshness: 24h             # optional; without it the port makes no freshness promise
access:
  readers:
    - grp-shop-reporting
    - product: agg_order_turnaround
  pii_readers: [grp-shop-support]
```

An input port fed by a source:

```yaml
schema_version: 1
kind: schema
source: jaffle_shop
schedule: "0 5 * * *"
```

An input port that reads another data product's output port has a folder named after that port, and no table files:

```yaml
schema_version: 1
from: sa_jaffle_orders
```

- A data product is identified in `product:` readers by its folder name, such as `agg_order_turnaround`.
- A port of kind `schema` holds any number of table files. A port of kind `table` has the same folder shape with exactly one table file.
- A reader is either a plain string, used as the warehouse role name as written, or `product: <data product>`, which maps to that data product's role. On DuckDB readers and PII readers are accepted and applied to nothing. See [Readers and personal data](concepts.md#readers-and-personal-data).
- `source` names the system that delivers the data, as free text. `dpb` connects nothing to it.
- `schedule` is a declared expectation in cron form: when the source delivers. The orchestrator runs it, not `dpb`.

## Table file

```yaml
schema_version: 1
name: orders
description: One row per jaffle shop order
columns:
  - name: order_id
    type: text
    rules: [not_null, unique]
  - name: customer_id
    type: text
    pii: true
  - name: status
    type: text
    rules:
      - rule: accepted_values
        values: [placed, shipped, completed, return_pending, returned]
        severity: warning
  - name: ordered_at
    type: timestamp
freshness_column: ordered_at
rules:
  - rule: row_count
    min: 1
build:
  executor: python
  entrypoint: src/orders.py:build
  params: {mode: full}
  needs: [ingested_orders]
```

- The top part is the contract and names no technology. The `build` block states how the table is made.
- Column types are free text, written as the warehouse spells them, and are not validated.
- Quality rules on a column: `not_null`, `unique`, `accepted_values`. On a table: `primary_key`, `row_count`, `sql`. A bare rule name uses the default severity.
- Severity is `error` (the run fails), `warning` (the run continues and reports) or `none` (the rule is ignored).
- A bare rule name is the short form and only works for `not_null` and `unique`. The long form is a mapping with `rule`, the rule's own keys and an optional `severity`: `values` for `accepted_values`, `columns` for `primary_key`, `min` and `max` for `row_count` and `sql` for `sql`.
- `freshness_column` names the column that holds the time of the newest data. It must be a column of the table. `dpb describe` shows it, and nothing measures it yet.
- `build.executor` is optional and defaults to the setting of the levels above it (`python` unless changed). `entrypoint` is `path/to/file.py:function`, relative to the data product folder.
- `params` are passed to the function as keyword arguments. They must be plain YAML values.
- `needs` lists the tables of the same data product that must be built first, in any of its ports. It must not contain a cycle.
- Table names are unique within a data product.

### Build code

The entrypoint is a plain Python function. It writes its table to the private schema of the data product, and connects to the warehouse by itself:

```python
# dataproducts/sa_jaffle_orders/src/orders.py
def build(mode: str = "full") -> None:
    """Build the table `orders` in the schema `sa_jaffle_orders_private`."""
    ...
```

The [tutorial](tutorial.md#9-write-the-build-code) has two complete functions for DuckDB, and [`examples/jaffle_shop`](https://github.com/datapatchbay/patchbay/tree/main/examples/jaffle_shop) has them for Postgres on Airflow.

### A table built by dbt

A table built by dbt has the same contract and no `build` block, when `executor: dbt` is set on its data product or higher. Its SQL is the dbt model `models/<dbt_model>.sql` in the data product's folder, and `dpb generate` writes the model's dbt properties from the table file. `entrypoint`, `params` and `needs` fail on it. See the [dbt reference](dbt.md).

## JSON Schema

`dpb schema` prints the JSON Schema of the four kinds of file. The schema checks the shape of one file, and not the rules across files. See [`dpb schema`](cli.md#dpb-schema) and [Set up your editor](howto/editor.md).
