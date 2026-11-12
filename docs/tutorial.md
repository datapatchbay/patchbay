# Tutorial: your first two data products

In this tutorial you start from an empty folder and end with two data products and their generated Airflow DAGs:

- `sa_ilab_orders` takes lab orders from a source and publishes them, with one column of personal data.
- `agg_lab_turnaround` reads that output port.

On the way, `dpb validate` stops two mistakes: a freshness promise that cannot be kept, and a data product that reads a port without permission.

You need `dpb` on your `PATH` (see [Installation](installation.md)). You need no warehouse and no Airflow, because `dpb` never connects to anything.

## 1. Start a repo

A datapatchbay repo is a folder with a `datapatchbay.yaml` at its root. One line is enough, because every setting has a default:

```console
$ mkdir lab && cd lab
$ echo "schema_version: 1" > datapatchbay.yaml
```

`dpb config` prints every setting and where its value comes from.

## 2. Scaffold a data product

Create a source-aligned data product named `ilab_orders`, fed by the source `ilab`:

```console
$ dpb new --name ilab_orders --kind source-aligned --domain operations --owner "Jane Doe" --source ilab --no-input
created dataproducts/sa_ilab_orders/dataproduct.yaml
created dataproducts/sa_ilab_orders/inputs/sa_ilab_orders_private/port.yaml
created dataproducts/sa_ilab_orders/inputs/sa_ilab_orders_private/ingested.yaml
created dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/port.yaml
created dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/example.yaml
created dataproducts/sa_ilab_orders/src/ingested.py
created dataproducts/sa_ilab_orders/src/example.py
```

Without `--no-input`, `dpb new` asks for each value you did not give as a flag.

You wrote the bare name `ilab_orders`. The folder is `sa_ilab_orders`, because the kind `source-aligned` has the prefix `sa` and the [naming templates](concepts.md#names-come-from-templates) put the two together. The same templates name the ports:

```text
dataproducts/sa_ilab_orders/
  dataproduct.yaml            owner, kind, domain, and the list of ports
  inputs/
    sa_ilab_orders_private/   the private input port, fed by the source
      port.yaml               source: ilab, schedule: "0 5 * * *"
      ingested.yaml           one table, as the source delivers it
  outputs/
    sa_ilab_orders/           the default output port
      port.yaml
      example.yaml            one example table
  src/
    ingested.py               a stub build function per table
    example.py
```

## 3. Validate it

```console
$ dpb validate
ok: 1 data product(s) valid
$ dpb list
DATA PRODUCT    KIND            DOMAIN      OWNER     TECHNICAL OWNER
sa_ilab_orders  source-aligned  operations  Jane Doe  -
```

The scaffold is valid before you edit it. Run `dpb validate` after every step below.

## 4. Write the contract of the output table

The example table is a placeholder. Rename it and its build code to `orders`:

```console
$ cd dataproducts/sa_ilab_orders
$ mv outputs/sa_ilab_orders/example.yaml outputs/sa_ilab_orders/orders.yaml
$ mv src/example.py src/orders.py
$ cd ../..
```

Replace the content of `dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/orders.yaml` with:

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

The output port states how fresh its data is and who may read it. Replace the content of `dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/port.yaml` with:

```yaml
schema_version: 1
kind: schema
freshness: 12h
access:
  readers: [grp-lab-reporting]
  pii_readers: [grp-lab-doctors]
```

`grp-lab-reporting` and `grp-lab-doctors` are roles in the warehouse. Both may read the port. Only `grp-lab-doctors` sees the values of `patient_id`, and everyone else sees NULL.

```console
$ dpb validate
dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/port.yaml:3: output port 'sa_ilab_orders' promises freshness 12h, but source input port 'sa_ilab_orders_private' delivers with a longest gap of 24h (schedule "0 5 * * *")
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
$ dpb new --name lab_turnaround --kind aggregate --domain operations --owner "Ann Poe" --no-input
created dataproducts/agg_lab_turnaround/dataproduct.yaml
created dataproducts/agg_lab_turnaround/outputs/agg_lab_turnaround/port.yaml
created dataproducts/agg_lab_turnaround/outputs/agg_lab_turnaround/example.yaml
created dataproducts/agg_lab_turnaround/src/example.py
```

A data product reads another one through an input port. That port is a folder named after the output port it reads, with a `port.yaml` and no tables:

```console
$ mkdir -p dataproducts/agg_lab_turnaround/inputs/sa_ilab_orders
```

Create `dataproducts/agg_lab_turnaround/inputs/sa_ilab_orders/port.yaml`:

```yaml
schema_version: 1
from: sa_ilab_orders
```

List the port in `dataproducts/agg_lab_turnaround/dataproduct.yaml`:

```yaml
schema_version: 1
name: lab_turnaround
kind: aggregate
domain: operations
owner: Ann Poe
inputs:
  - sa_ilab_orders
outputs:
  - agg_lab_turnaround
```

```console
$ dpb validate
dataproducts/agg_lab_turnaround/inputs/sa_ilab_orders/port.yaml:2: data product 'agg_lab_turnaround' reads 'sa_ilab_orders' but is not listed in the readers of that port; add `- product: agg_lab_turnaround` under access.readers in dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/port.yaml
1 problem(s) found
```

Declaring an input port is not the same as having access. The owner of `sa_ilab_orders` has to list the new reader, and in a team that change goes through a pull request. Do what the message says, in `dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/port.yaml`:

```yaml
schema_version: 1
kind: schema
freshness: 24h
access:
  readers:
    - grp-lab-reporting
    - product: agg_lab_turnaround
  pii_readers: [grp-lab-doctors]
```

```console
$ dpb validate
ok: 2 data product(s) valid
```

## 7. Look at one data product

`dpb describe` prints one data product with every setting resolved. The part about the output port now shows the readers, and the data product that reads it:

```console
$ dpb describe sa_ilab_orders
...
    output port sa_ilab_orders  (dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/port.yaml)
      kind: schema
      freshness: 24h
      readers: grp-lab-reporting, product:agg_lab_turnaround
      pii readers: grp-lab-doctors
      read by: agg_lab_turnaround
...
        columns:
          order_id text
            rule: not_null [error, from defaults]
            rule: unique [error, from defaults]
          patient_id text pii
          status text
            rule: accepted_values values=['open', 'closed'] [warning, from rule]
          ordered_at timestamp
```

## 8. Generate the DAGs

```console
$ dpb generate
wrote /path/to/lab/generated/agg_lab_turnaround.py
wrote /path/to/lab/generated/sa_ilab_orders.py
ok: 2 file(s) written to /path/to/lab/generated
```

Each file is one Airflow 3 DAG. Open `generated/sa_ilab_orders.py` and you find:

- The schedule of the source, `0 5 * * *`.
- A build task per table, each followed by an audit task that runs the table's quality rules: `build_ingested`, `audit_ingested`, `build_orders`, `audit_orders`. `orders` waits for the audit of `ingested`, because it `needs` it.
- `apply_access`, which creates the views of the output port, hides `patient_id` from everyone but the PII readers, and grants the readers access.
- `publish_outputs`, which marks the output port as updated.

`generated/agg_lab_turnaround.py` has no cron schedule. It runs when the output port `sa_ilab_orders` is updated.

The files are build output, so keep them out of git:

```console
$ echo "generated/" >> .gitignore
```

## 9. What is left

The files in `src/` are stubs that raise `NotImplementedError`. To run the DAGs for real:

1. Replace each stub with code that writes its table to the data product's private schema in the warehouse, such as `sa_ilab_orders_private`. Build code never writes to an output port: the views there are generated.
2. Rename the example table of `agg_lab_turnaround` and write its contract, as you did in step 4.
3. Create the roles in the warehouse. The generated SQL grants to `grp-lab-reporting`, `grp-lab-doctors` and `dp_agg_lab_turnaround`, and never creates them.
4. Deploy the repo and the generated files to Airflow. See [Deploy the generated DAGs](howto/deploy.md).

[`examples/lab`](https://github.com/datapatchbay/patchbay/tree/main/examples/lab) is the finished version of this tutorial, with build code for Postgres. The CI of datapatchbay runs both of its DAGs against a real Postgres.

## Next

- [Validate in CI](howto/ci.md), so a broken contract never reaches `main`.
- [How it works](concepts.md) explains ports, readers, freshness and quality rules.
- The [file reference](files.md) lists every key of the four kinds of file.
