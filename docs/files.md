# File reference

This page covers schema version 1.

## Repository layout

```text
datapatchbay.yaml
dataproducts/
  sa_ilab_orders/
    dataproduct.yaml
    inputs/
      sa_ilab_orders_private/
        port.yaml
        ingested_orders.yaml
    outputs/
      sa_ilab_orders/
        port.yaml
        orders.yaml
    src/
      ingested_orders.py
      orders.py
  agg_lab_turnaround/
    dataproduct.yaml
    inputs/
      sa_ilab_orders/
        port.yaml
    outputs/
      agg_lab_turnaround/
        port.yaml
        turnaround.yaml
    models/
      agg_lab_turnaround__turnaround.sql
      agg_lab_turnaround__turnaround.yml   # generated, committed
dbt_project.yml                            # only for dbt; `dpb generate` keeps its `model-paths` in step
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
warehouse: postgres
orchestrator: airflow
executor: python
runtime: worker            # worker | docker | kubernetes
severity: error            # default severity of quality rules
connection: warehouse      # the orchestrator's connection to the warehouse
output_dir: generated      # where `dpb generate` writes, relative to the repo root
dbt:
  project_dir: .           # the dbt project on the worker; relative to the repo root as deployed with the DAG files
  profiles_dir: ~/.dbt     # the folder with profiles.yml on the worker
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
    dbt_model: "{dataproduct}__{table}"
```

A naming template may use `{name}` (the data product's bare name), `{kind.prefix}` and `{kind.name}`. The `dbt_model` template also has `{dataproduct}` (the data product's derived name) and `{table}`, because dbt model names must be unique across a dbt project. `dpb validate` compares the folder name, the default output port name and the private port name with what the templates produce, so changing a prefix or a template changes what it expects.

See [Settings and plugins](settings.md) for how these values merge with the defaults and with settings lower down.

## `dataproduct.yaml`

```yaml
schema_version: 1
name: ilab_orders
kind: source-aligned
domain: operations
owner: Jane Doe
technical_owner: John Roe
description: Lab orders as received from the lab system
inputs: [sa_ilab_orders_private]
outputs: [sa_ilab_orders]
```

- `name` is written without the kind's prefix. Naming templates produce the folder name, the port names and the role name.
- `owner` and `technical_owner` are people, written as free text and not validated.
- `kind` must be one of the kinds in the conventions. It is a label, and it does not restrict what a data product may read.
- `inputs` and `outputs` list port names and must match the folders.

## `port.yaml`

An output port:

```yaml
schema_version: 1
kind: schema               # schema | table
freshness: 24h             # optional; without it the port makes no freshness promise
access:
  readers:
    - grp-lab-reporting
    - product: agg_lab_turnaround
  pii_readers: [grp-lab-doctors]
```

An input port fed by a source:

```yaml
schema_version: 1
kind: schema
source: ilab
schedule: "0 5 * * *"
```

An input port that reads another data product's output port has a folder named after that port, and no table files:

```yaml
schema_version: 1
from: sa_ilab_orders
```

- A data product is identified in `product:` readers by its folder name, such as `agg_lab_turnaround`.
- A port of kind `schema` holds any number of table files. A port of kind `table` has the same folder shape with exactly one table file.
- A reader is either a plain string, used as the warehouse role name as written, or `product: <data product>`, which maps to that data product's role.
- `schedule` is a declared expectation in cron form. The orchestrator runs it, not `dpb`.

## Table file

```yaml
schema_version: 1
name: orders
description: One row per lab order
columns:
  - name: order_id
    type: text
    rules: [not_null, unique]
  - name: patient_id
    type: text
    pii: true
  - name: status
    type: text
    rules:
      - rule: accepted_values
        values: [open, closed]
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
- `build.executor` is optional and defaults to the setting of the levels above it (`python` unless changed). `entrypoint` is `path/to/file.py:function`, relative to the data product folder.
- `needs` lists the tables of the same data product that must be built first, in any of its ports. It must not contain a cycle.
- Table names are unique within a data product.

A table built by dbt has the same contract and no `build` block when `executor: dbt` is set on its data product or higher (or `build: {executor: dbt}` on the table itself). `entrypoint`, `params` and `needs` fail on it, because dbt takes the order from the model's `ref()` calls. Its SQL is the dbt model `models/<dbt_model>.sql` in the data product's folder, named by the `dbt_model` naming template in `conventions.names`, by default `{dataproduct}__{table}`; a missing model file fails, and so does a `.py` file anywhere in a `models/` folder, because dbt would read it as a dbt Python model. A table rule (`primary_key`, `row_count`, `sql`) fails on it with "not supported for dbt yet", until the mapping of table rules to dbt is decided. Any other table needs a `build.entrypoint`. `dpb generate` writes the model's dbt properties from the table file; nobody writes them by hand.

The generated properties put each model in its data product's private schema with `config: {schema: <private port name>}`. By default dbt does not use that name as written: it builds `<target schema>_<custom schema>`. For models to land in the private schema as written, the team's dbt project must override the `generate_schema_name` macro, for example in `macros/generate_schema_name.sql`:

```jinja
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name | trim if custom_schema_name is not none else target.schema }}
{%- endmacro %}
```

`dpb generate` does not write or check this macro, because it never reads the macros of the dbt project (the folder is also not a `model-paths` entry). Without it, tables are created in a schema such as `<target schema>_<private port name>` and the grants and masking views, which name the private port, do not find them.

## JSON Schema

`dpb schema` prints the JSON Schema of the four kinds of file, so an editor or an agent can validate a file before writing it.

```sh
dpb schema root         # datapatchbay.yaml
dpb schema dataproduct  # dataproduct.yaml
dpb schema port         # port.yaml, in its three forms
dpb schema table        # a table file
dpb schema              # all four, as one JSON object keyed by kind
```

The schema is generated from the same models `dpb validate` uses. It accepts the short form of a column rule, a bare `not_null` or `unique`. The schema checks the shape of a file; the cross-file checks of `dpb validate` (names, folders, readers, freshness) are not in it. [Set up your editor](howto/editor.md) shows how to point an editor at the schema.
