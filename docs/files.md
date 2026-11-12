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
```

There are four kinds of file:

- `datapatchbay.yaml` at the root
- per data product, one `dataproduct.yaml`
- one `port.yaml` per port
- one YAML file per table

The Python code of a data product lives in its folder.

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
```

A naming template may use `{name}` (the data product's bare name), `{kind.prefix}` and `{kind.name}`. `dpb validate` compares the folder name, the default output port name and the private port name with what the templates produce, so changing a prefix or a template changes what it expects.

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
- `build.executor` is required and must be `python`. `entrypoint` is `path/to/file.py:function`, relative to the data product folder.
- `needs` lists the tables of the same data product that must be built first, in any of its ports. It must not contain a cycle.
- Table names are unique within a data product.

## JSON Schema

`dpb schema` prints the JSON Schema of the four kinds of file, so an editor or an agent can validate a file before writing it.
