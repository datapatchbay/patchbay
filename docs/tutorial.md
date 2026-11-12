# Tutorial: your first two data products

In this tutorial you start from an empty folder and end with two data products and their generated Airflow DAGs:

- `sa_jaffle_orders` takes jaffle shop orders from a source and publishes them, with one column of personal data.
- `agg_order_turnaround` reads that output port.

On the way, `dpb validate` stops two mistakes: a freshness promise that cannot be kept, and a data product that reads a port without permission.

You need `dpb` on your `PATH` (see [Installation](installation.md)). You need no warehouse and no Airflow, because `dpb` never connects to anything.

## 1. Start a repo

A datapatchbay repo is a folder with a `datapatchbay.yaml` at its root. One line is enough, because every setting has a default:

```console
$ mkdir jaffle_shop && cd jaffle_shop
$ echo "schema_version: 1" > datapatchbay.yaml
```

`dpb config` prints every setting and where its value comes from.

## 2. Scaffold a data product

Create a source-aligned data product named `jaffle_orders`, fed by the source `jaffle_shop`:

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
freshness_column: ordered_at
build:
  entrypoint: src/orders.py:build
  needs: [ingested]
```

The part above `build` is the contract: the columns, the column with personal data, and the quality rules. A domain expert can read it and confirm it. The `build` block says which function makes the table, and that the table `ingested` comes first.

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

`grp-shop-reporting` and `grp-shop-support` are roles in the warehouse. Both may read the port. Only `grp-shop-support` sees the values of `customer_id`, and everyone else sees NULL.

```console
$ dpb validate
dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/port.yaml:3: output port 'sa_jaffle_orders' promises freshness 12h, but source input port 'sa_jaffle_orders_private' delivers with a longest gap of 24h (schedule "0 5 * * *")
1 problem(s) found
```

The source delivers once a day, so the port cannot promise data that is at most 12 hours old. `dpb validate` found that from the files alone. Change `freshness` to `24h`:

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

## 9. What is left

The files in `src/` are stubs that raise `NotImplementedError`. To run the DAGs for real:

1. Replace each stub with code that writes its table to the data product's private schema in the warehouse, such as `sa_jaffle_orders_private`. Build code never writes to an output port: the views there are generated.
2. Rename the example table of `agg_order_turnaround` and write its contract, as you did in step 4.
3. Create the roles in the warehouse. The generated SQL grants to `grp-shop-reporting`, `grp-shop-support` and `dp_agg_order_turnaround`, and never creates them.
4. Deploy the repo and the generated files to Airflow. See [Deploy the generated DAGs](howto/deploy.md).

[`examples/jaffle_shop`](https://github.com/datapatchbay/patchbay/tree/main/examples/jaffle_shop) is the finished version of this tutorial, with build code for Postgres. The CI of datapatchbay runs both of its DAGs against a real Postgres.

## Next

- [Validate in CI](howto/ci.md), so a broken contract never reaches `main`.
- [How it works](concepts.md) explains ports, readers, freshness and quality rules.
- The [file reference](files.md) lists every key of the four kinds of file.
