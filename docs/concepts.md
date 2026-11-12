# How it works

A data platform described as a set of owned data products. Each one declares what it reads, what it publishes and what it promises. `dpb` checks those declarations and generates the files that put them into effect. It never touches the warehouse itself.

```text
YAML in the repo
  ├── dpb validate  →  fails CI on a broken contract
  └── dpb generate  →  Airflow DAGs + Postgres SQL  →  run by the orchestrator
```

## Data products

A **data product** is a named, owned unit of data on the platform. It reads through input ports and publishes through output ports. Each data product is one folder.

- The **owner** is the person accountable for it, and the one to call when a number is wrong.
- The **technical owner** is the person who builds and maintains it.
- Its **domain** is the business area it belongs to, such as finance, sales or operations.
- Its **kind** is a label from a list the platform defines: by default source-aligned, aggregate or consumer-aligned. A kind does not restrict what a data product may read.

Owners are people written as free text. There is no registry of teams to fill in before the first data product exists.

## Names come from templates

A data product states a bare name, such as `ilab_orders`, and a kind with a prefix, such as `sa`. Every other name is produced by a **naming template**: the folder name, the output port name, the private port name and the role name. A team's naming convention lives in one place, and port names are unique across the repo by construction.

```text
name: ilab_orders  +  kind: source-aligned (prefix sa)
  ├── folder and default output port   sa_ilab_orders
  ├── private input port               sa_ilab_orders_private
  └── warehouse role                   dp_sa_ilab_orders
```

## Ports

A **port** is a named interface through which data enters or leaves a data product. Each port is a folder with its own `port.yaml` and one file per table. A port mirrors one schema in the warehouse.

Input port
: Receives data, either from a **source** (a system outside the platform) or from another data product's output port.

Output port
: Publishes data, with its own freshness promise and access policy. The **default output port** carries the same name as its data product.

A port of kind `schema` holds any number of tables. A port of kind `table` has the same folder shape with exactly one table. Files, APIs and scheduled exports may follow as port kinds later.

## Output ports are views over private tables

A data product lands its ingested tables and builds its output tables in its **private schema**. Nobody outside the data product reads it.

An output port holds only generated views over those private tables. Readers are granted access to the views, never to the tables. Build code never writes to an output port.

## Readers and personal data

An output port lists its **readers**, the roles allowed to read it:

- A plain string is used as the warehouse role name as written.
- `product: <data product>` maps to that data product's role.

**PII readers** may also see the columns marked as personal data. In the view, a PII column shows its value to PII readers and NULL to everyone else, and both groups query the same object.

Reading is not the same as access. A data product that declares an input port on someone else's output port must also be listed in that port's readers, and `dpb validate` fails if it is not. That way the owner of a port approves every new reader in a pull request.

## Freshness

**Freshness** is a promise of how old the newest data in an output port may be, stated as a duration such as `24h`. `dpb validate` checks that an output port does not promise fresher data than its inputs deliver. It compares the port's freshness with the schedule of its source input ports and the freshness of the output ports it reads.

## Contract and build

Each table file has two parts:

Contract
: The columns and quality rules expected of the table. It names no technology.

Build
: How the table is made: its **executor** (Python or dbt), the entrypoint, its parameters, and the tables of the same data product it needs first.

The build block can be swapped without touching the contract.

## Quality rules

A **quality rule** is a condition the data must meet. Column rules are `not_null`, `unique` and `accepted_values`. Table rules are `primary_key`, `row_count` and `sql`.

Each rule has a **severity**:

| Severity | When the rule is broken |
| --- | --- |
| `error` | The run fails |
| `warning` | The run continues and reports it |
| `none` | The rule is ignored |

Rules run as generated audit tasks in the orchestrator, after the table's build task. In milestone 1 the data is already visible when a rule fails. Write-audit-publish, planned for milestone 3, closes that gap. A table built by dbt runs its rules as dbt data tests instead.

## What runs where

`dpb` reads YAML and writes files. It holds no credentials and ships no database driver.

- The **orchestrator** (Airflow) triggers builds on a schedule, and runs the generated audits, views and grants through a connection that already exists there.
- The **runtime** is where build code runs: on the Airflow worker, or in a Docker or Kubernetes container.
- Build code connects by itself. On the worker it can use the orchestrator's connection. In a container it reads what the team put in the container's environment.

A change to access takes effect on the next run of the data product's DAG, not at merge time.

## Why it works this way

Each design decision is recorded with the options that were considered and what follows from it, in [`docs/adr`](https://github.com/datapatchbay/patchbay/tree/main/docs/adr) of the repo. Start with [`dpb` never connects to the warehouse](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0001-dpb-never-connects-to-the-warehouse.md) and [output ports are views over private tables](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0002-output-ports-are-views-over-private-tables.md).

To see the model at work, follow the [tutorial](tutorial.md).
