# Tutorial: your first two data products

In this tutorial you start from an empty folder and end with two data products:

- `sa_jaffle_orders` takes jaffle shop orders from a source and publishes them, with one column of personal data.
- `agg_order_turnaround` reads that output port.

On the way, `dpb validate` stops two mistakes: a freshness promise that cannot be kept, and a data product that reads a port without permission. At the end you run the first data product on your machine and query what it publishes.

If the words data product and port are new to you, read [What is a data product](data-products.md) first.

You need [uv](https://docs.astral.sh/uv/) and `dpb`:

```sh
uv tool install git+https://github.com/datapatchbay/patchbay
```

You need no warehouse server and no Airflow. `dpb` never connects to anything, and the last steps use DuckDB, a database in one file.

## 1. Start a repo

A datapatchbay repo is a folder with a `datapatchbay.yaml` at its root. One line is enough, because every setting has a default:

```console
$ mkdir jaffle_shop && cd jaffle_shop
$ echo "schema_version: 1" > datapatchbay.yaml
```

`dpb config` prints every setting and where its value comes from.

## 2. Scaffold a data product

Create a data product named `jaffle_orders`, fed by the source `jaffle_shop`:

```console
$ dpb new --name jaffle_orders --kind source-aligned --domain operations --owner "Jane Doe" --source jaffle_shop --no-input
created dataproducts/sa_jaffle_orders/dataproduct.yaml
created dataproducts/sa_jaffle_orders/inputs/sa_jaffle_orders_private/port.yaml
created dataproducts/sa_jaffle_orders/inputs/sa_jaffle_orders_private/ingested.yaml
created dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/port.yaml
created dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/example.yaml
created dataproducts/sa_jaffle_orders/src/ingested.py
created dataproducts/sa_jaffle_orders/src/example.py
```

Without `--no-input`, `dpb new` asks for each value you did not give as a flag.

Two of the flags need a word:

- `--kind source-aligned` says that this data product publishes the data of one source system as it is. The other two kinds are aggregate and consumer-aligned. See [Three kinds of data product](data-products.md#three-kinds-of-data-product).
- `--source jaffle_shop` names the system that the data comes from. The name is free text for people to read. `dpb` connects nothing to it: you write the code that fetches the data, in step 9.

You wrote the bare name `jaffle_orders`. The folder is `sa_jaffle_orders`, because the kind `source-aligned` has the prefix `sa` and the [naming templates](concepts.md#names-come-from-templates) put the two together. The same templates name the ports:

```text
dataproducts/sa_jaffle_orders/
  dataproduct.yaml              owner, kind, domain, and the list of ports
  inputs/
    sa_jaffle_orders_private/   the private input port, fed by the source
      port.yaml                 source: jaffle_shop, schedule: "0 5 * * *"
      ingested.yaml             one table, as the source delivers it
  outputs/
    sa_jaffle_orders/           the default output port
      port.yaml
      example.yaml              one example table
  src/
    ingested.py                 a stub build function per table
    example.py
```

Each YAML file below a port describes one table. The data product builds all its tables in its **private schema**, `sa_jaffle_orders_private`, which only its own code uses. The output port `sa_jaffle_orders` becomes a second schema that holds a view of each table under `outputs/`. Other people and data products read those views. [How it works](concepts.md#output-ports-are-views-over-private-tables) has the picture.

## 3. Validate it

```console
$ dpb validate
ok: 1 data product(s) valid
$ dpb list
DATA PRODUCT      KIND            DOMAIN      OWNER     TECHNICAL OWNER
sa_jaffle_orders  source-aligned  operations  Jane Doe  -
```

The scaffold is valid before you edit it. Run `dpb validate` after every step below.

## 4. Write the contract of the output table

The example table is a placeholder. Rename it and its build code to `orders`:

```console
$ cd dataproducts/sa_jaffle_orders
$ mv outputs/sa_jaffle_orders/example.yaml outputs/sa_jaffle_orders/orders.yaml
$ mv src/example.py src/orders.py
$ cd ../..
```

Replace the content of `dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/orders.yaml` with:

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
build:
  entrypoint: src/orders.py:build
  needs: [ingested]
```

The part above `build` is the contract: the columns, the column with personal data (`pii: true`), and the quality rules. A domain expert can read it and confirm it. A broken rule fails the run, except a rule with `severity: warning`, which only reports.

The `build` block says which function makes the table, and that the table `ingested` comes first.

```console
$ dpb validate
ok: 1 data product(s) valid
```

## 5. Promise freshness and name the readers

The output port states how fresh its data is and who may read it. Replace the content of `dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/port.yaml` with:

```yaml
schema_version: 1
kind: schema
freshness: 12h
access:
  readers: [grp-shop-reporting]
  pii_readers: [grp-shop-support]
```

- `kind: schema` says that the port is a schema that can hold several tables.
- `freshness: 12h` promises that the newest data in the port is at most 12 hours old.
- `grp-shop-reporting` and `grp-shop-support` are roles in the warehouse. Both may read the port. Only `grp-shop-support` sees the values of `customer_id`, and everyone else sees NULL.

```console
$ dpb validate
dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/port.yaml:3: output port 'sa_jaffle_orders' promises freshness 12h, but source input port 'sa_jaffle_orders_private' delivers with a longest gap of 24h (schedule "0 5 * * *")
1 problem(s) found
```

The source delivers once a day, at 05:00, so the port cannot promise data that is at most 12 hours old. `dpb validate` found that from the files alone. Change `freshness` to `24h`:

```console
$ dpb validate
ok: 1 data product(s) valid
```

## 6. Add a data product that reads the first one

Scaffold an aggregate. It has no source, so leave out `--source`:

```console
$ dpb new --name order_turnaround --kind aggregate --domain operations --owner "Ann Poe" --no-input
created dataproducts/agg_order_turnaround/dataproduct.yaml
created dataproducts/agg_order_turnaround/outputs/agg_order_turnaround/port.yaml
created dataproducts/agg_order_turnaround/outputs/agg_order_turnaround/example.yaml
created dataproducts/agg_order_turnaround/src/example.py
```

A data product reads another one through an input port. That port is a folder named after the output port it reads, with a `port.yaml` and no tables:

```console
$ mkdir -p dataproducts/agg_order_turnaround/inputs/sa_jaffle_orders
```

Create `dataproducts/agg_order_turnaround/inputs/sa_jaffle_orders/port.yaml`:

```yaml
schema_version: 1
from: sa_jaffle_orders
```

List the port in `dataproducts/agg_order_turnaround/dataproduct.yaml`:

```yaml
schema_version: 1
name: order_turnaround
kind: aggregate
domain: operations
owner: Ann Poe
inputs:
  - sa_jaffle_orders
outputs:
  - agg_order_turnaround
```

```console
$ dpb validate
dataproducts/agg_order_turnaround/inputs/sa_jaffle_orders/port.yaml:2: data product 'agg_order_turnaround' reads 'sa_jaffle_orders' but is not listed in the readers of that port; add `- product: agg_order_turnaround` under access.readers in dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/port.yaml
1 problem(s) found
```

Declaring an input port is not the same as having access. The owner of `sa_jaffle_orders` has to list the new reader, and in a team that change goes through a pull request. Do what the message says, in `dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/port.yaml`:

```yaml
schema_version: 1
kind: schema
freshness: 24h
access:
  readers:
    - grp-shop-reporting
    - product: agg_order_turnaround
  pii_readers: [grp-shop-support]
```

```console
$ dpb validate
ok: 2 data product(s) valid
```

## 7. Look at one data product

`dpb describe` prints one data product with every setting resolved. The part about the output port now shows the readers, and the data product that reads it:

```console
$ dpb describe sa_jaffle_orders
...
    output port sa_jaffle_orders  (dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/port.yaml)
      kind: schema
      freshness: 24h
      readers: grp-shop-reporting, product:agg_order_turnaround
      pii readers: grp-shop-support
      read by: agg_order_turnaround
...
        columns:
          order_id text
            rule: not_null [error, from defaults]
            rule: unique [error, from defaults]
          customer_id text pii
          status text
            rule: accepted_values values=['placed', 'shipped', 'completed', 'return_pending', 'returned'] [warning, from rule]
          ordered_at timestamp
```

## 8. Generate the DAGs

`dpb generate` turns the files into something an orchestrator can run. By default that is Airflow, where the unit that runs is called a DAG:

```console
$ dpb generate
wrote /path/to/jaffle_shop/generated/agg_order_turnaround.py
wrote /path/to/jaffle_shop/generated/sa_jaffle_orders.py
ok: 2 file(s) written (2 to /path/to/jaffle_shop/generated), 0 removed
```

Each file is one Airflow 3 DAG. Open `generated/sa_jaffle_orders.py` and you find:

- The schedule of the source, `0 5 * * *`.
- A build task per table, each followed by an audit task that runs the table's quality rules: `build_ingested`, `audit_ingested`, `build_orders`, `audit_orders`. `orders` waits for the audit of `ingested`, because it `needs` it.
- `apply_access`, which creates the views of the output port, hides `customer_id` from everyone but the PII readers, and grants the readers access.
- `publish_outputs`, which marks the output port as updated.

`generated/agg_order_turnaround.py` has no cron schedule. It runs when the output port `sa_jaffle_orders` is updated.

The files are build output, so keep them out of git:

```console
$ echo "generated/" >> .gitignore
```

## 9. Write the build code

The files in `src/` are stubs that raise `NotImplementedError`. Build code is a plain Python function. It takes the `params` of the table's `build` block as keyword arguments, and these tables have none. It connects to the warehouse by itself, and writes its table to the private schema of the data product. It never writes to an output port: the views there are generated.

The two functions below use DuckDB, and read the path of the database file from an environment variable that you choose.

Replace the content of `dataproducts/sa_jaffle_orders/src/ingested.py` with a function that lands the orders of the source. A real one would call the API of the shop's order system or read its export:

```python
"""Build code of the table `ingested`."""

import os

import duckdb

ORDERS = [
    ("JO-1", "C-100", "completed", "2025-03-03 08:00"),
    ("JO-2", "C-101", "shipped", "2025-03-03 09:30"),
    ("JO-3", "C-102", "placed", "2025-03-04 10:15"),
]


def build() -> None:
    """Land the orders of the shop in the private schema, as the source delivers them."""
    with duckdb.connect(os.environ["WAREHOUSE_FILE"]) as db:
        db.execute("CREATE SCHEMA IF NOT EXISTS sa_jaffle_orders_private")
        db.execute(
            "CREATE OR REPLACE TABLE sa_jaffle_orders_private.ingested"
            " (id TEXT, customer_id TEXT, status TEXT, ordered_at TIMESTAMP)"
        )
        db.executemany("INSERT INTO sa_jaffle_orders_private.ingested VALUES (?, ?, ?, ?)", ORDERS)
```

Replace the content of `dataproducts/sa_jaffle_orders/src/orders.py` with a function that builds `orders` from it:

```python
"""Build code of the table `orders`."""

import os

import duckdb


def build() -> None:
    """Build `orders` in the private schema from the ingested orders."""
    with duckdb.connect(os.environ["WAREHOUSE_FILE"]) as db:
        db.execute(
            "CREATE OR REPLACE TABLE sa_jaffle_orders_private.orders AS"
            " SELECT id AS order_id, customer_id, status, ordered_at FROM sa_jaffle_orders_private.ingested"
        )
```

The table file of `ingested` still has the one column `id` of the scaffold. A real contract lists every column, as you did for `orders`.

## 10. Run it on your machine

To run a data product without Airflow, let `dpb` generate a plain Python script instead of a DAG, for DuckDB instead of Postgres. Replace the content of `datapatchbay.yaml` with:

```yaml
schema_version: 1
orchestrator: local
warehouse: duckdb
```

Generate again, then run the script of the first data product. `WAREHOUSE_FILE` is the variable that your build code reads, and `DPB_CONNECTION_WAREHOUSE` is the one that the script reads:

```console
$ dpb generate
$ export WAREHOUSE_FILE=warehouse.duckdb
$ export DPB_CONNECTION_WAREHOUSE=duckdb:warehouse.duckdb
$ uv run --with duckdb python generated/sa_jaffle_orders.py
INFO sa_jaffle_orders: build_ingested
INFO sa_jaffle_orders: audit_ingested
INFO sa_jaffle_orders: build_orders
INFO sa_jaffle_orders: audit_orders
INFO sa_jaffle_orders: apply_access
```

These are the tasks of the DAG in step 8, run once and in order. Each log line starts with the time, left out here. Now read the output port as a reader would:

```console
$ uv run --with duckdb python -c "import duckdb; duckdb.connect('warehouse.duckdb').sql('SELECT * FROM sa_jaffle_orders.orders').show()"
┌──────────┬─────────────┬───────────┬─────────────────────┐
│ order_id │ customer_id │  status   │     ordered_at      │
│ varchar  │   varchar   │  varchar  │      timestamp      │
├──────────┼─────────────┼───────────┼─────────────────────┤
│ JO-1     │ NULL        │ completed │ 2025-03-03 08:00:00 │
│ JO-2     │ NULL        │ shipped   │ 2025-03-03 09:30:00 │
│ JO-3     │ NULL        │ placed    │ 2025-03-04 10:15:00 │
└──────────┴─────────────┴───────────┴─────────────────────┘
```

`sa_jaffle_orders.orders` is the view of the output port, over the table `sa_jaffle_orders_private.orders`. The column `customer_id` is NULL because it is marked `pii: true`. DuckDB has no roles, so it shows NULL to everyone. On Postgres, the PII readers see the values.

Try a broken rule: change one `id` in `ORDERS` to `None` and run the script again. `audit_ingested` fails with `quality rule 'not_null' is broken on table 'ingested', column 'id': 1 violation(s)`, and the script stops before it builds `orders`.

[Run a data product without an orchestrator](howto/local.md) describes the script.

## What is left

To run the data products in production:

1. Set `orchestrator` and `warehouse` in `datapatchbay.yaml` to what you run. Removing both lines gives Airflow and Postgres. Write the build code for that warehouse: [`examples/jaffle_shop`](https://github.com/datapatchbay/patchbay/tree/main/examples/jaffle_shop) is the finished version of this tutorial, with build code for Postgres.
2. Rename the example table of `agg_order_turnaround`, write its contract and its build code, as you did for `orders`.
3. Create the roles in the warehouse. The generated SQL grants to `grp-shop-reporting`, `grp-shop-support` and `dp_agg_order_turnaround`, and never creates them. `dp_agg_order_turnaround` is the role of the reading data product: its build code connects with a login that is a member of that role.
4. Deploy the repo and the generated files to the orchestrator. See [Deploy the generated DAGs](howto/deploy.md).

## Next

- [Validate in CI](howto/ci.md), so a broken contract never reaches `main`.
- [How it works](concepts.md) explains ports, readers, freshness and quality rules.
- [Limits and guarantees](limits.md) lists what to expect in production.
- The [file reference](files.md) lists every key of the four kinds of file.
