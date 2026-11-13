# datapatchbay

Data products as code. Declare owners, ports and freshness in YAML, then scaffold, validate and generate from one lightweight CLI.

Status: design agreed, nothing released. Command `dpb`. License Apache 2.0.

Terms in this document are defined in [GLOSSARY.md](GLOSSARY.md). Decisions and their reasons are in [docs/adr/](docs/adr/).

## What it is

A file-based CLI that turns a data platform into a set of owned data products. Each data product is a folder of YAML files that state who owns it, what it reads, what it publishes, how fresh each output is and who may read it. The CLI scaffolds those folders, validates them in CI, and generates the orchestrator and warehouse files that put them into effect.

The name comes from the patchbay behind a mixing console: every input and output has a labelled jack, and you route by declaring connections.

## The problem

Small and mid-size data teams hit the same four issues once more than one person or domain is involved:

- Nobody owns a table. When a number is wrong, there is no name to call.
- Everything is public. Consumers join straight into intermediate tables, so every refactor breaks a report.
- The same concept has several names, and each gets a different count.
- Access is handled by hand, so nobody can safely query the warehouse directly, and neither can an AI agent.

Data mesh gave teams the vocabulary for this and no implementation. The goal here is that creating a data product takes five minutes.

## Who it is for

- A central data team on a single platform that wants ownership and contracts without buying a catalog.
- A company where a second or third team starts building on the same warehouse.
- Teams of 2 to 20 engineers, usually with one monorepo.

## Principles

- **Lightweight.** Three dependencies: Pydantic, Typer and ruamel.yaml. Managed and distributed with uv.
- **`dpb` never connects to the warehouse.** It reads YAML and writes files. The orchestrator and the runtime do all the connecting.
- **Generated files stand alone.** They do not import datapatchbay. If someone deletes datapatchbay, the DAGs still run.
- **No scheduler.** The orchestrator schedules; `dpb` generates what it runs.
- **CLI and files, no UI.** Approvals happen in pull requests.
- **Defaults for everything.** A team writes down only where it differs.
- **Built for agents.** `--json` output, a published JSON Schema, and a mode that fails instead of prompting.

## Repository layout

```
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
dbt_project.yml                              # only for dbt
```

There are four kinds of file: `datapatchbay.yaml` at the root, and per data product one `dataproduct.yaml`, one `port.yaml` per port and one YAML per table. The build code of a data product lives in its folder: Python modules in `src/`, dbt models in `models/` (ADR-0015). A team chooses Python or dbt per data product, or per table.

## The schema, version 1

Every file carries `schema_version`. Unknown keys fail validation. Every file accepts a free-form `meta` map for a team's own extras.

### datapatchbay.yaml

Holds the settings that apply to all data products. Defaults ship inside the package, so this file holds only the changes and can be one line long.

```yaml
schema_version: 1
warehouse: postgres
orchestrator: airflow
executor: python
runtime: worker            # worker | docker | kubernetes
severity: error            # default severity of quality rules
connection: warehouse      # the orchestrator's connection to the warehouse
output_dir: generated      # where `dpb generate` writes, relative to the repo root
dbt:                       # declared by the dbt plugin (ADR-0025)
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

### dataproduct.yaml

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
- `kind` must be one of the kinds in the conventions. It is a label; it does not restrict what a data product may read.
- `inputs` and `outputs` list port names and must match the folders.

### port.yaml

An output port:

```yaml
schema_version: 1
kind: schema               # schema | table
freshness: 24h
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

An input port that reads another data product's output port has a folder named after that port and no table files:

```yaml
schema_version: 1
from: sa_jaffle_orders
```

- A port of kind `schema` holds any number of table files. A port of kind `table` has the same folder shape with exactly one table file.
- A reader is a plain string, used as the warehouse role name as written, or `product: <data product>`, which maps to that data product's role.
- `schedule` is a declared expectation in cron form. The orchestrator runs it; `dpb` does not.

### Table file

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
- Column types are free text and not validated.
- Quality rules on a column: `not_null`, `unique`, `accepted_values`. On a table: `primary_key`, `row_count`, `sql`. A bare rule name uses the default severity.
- Severity is `error` (the run fails), `warning` (the run continues and reports) or `none` (the rule is ignored).
- `needs` lists the tables of the same data product that must be built first.

A table built by dbt has the same contract and no `build` block when `executor: dbt` is set on its data product or higher (or `build: {executor: dbt}` on the table itself). `entrypoint`, `params` and `needs` fail on it, because dbt takes the order from the model's `ref()` calls. Its SQL is the dbt model `models/<dbt_model>.sql` in the data product's folder, named by the `dbt_model` naming template in `conventions.names`, by default `{dataproduct}__{table}`; a missing model file fails, and so does a `.py` file anywhere in a `models/` folder, because dbt would read it as a dbt Python model. A table rule (`primary_key`, `row_count`, `sql`) becomes a generated singular dbt data test, one SQL file per rule in the data product's `tests/` folder (ADR-0019). Each rule's SQL selects the rows that break it: `primary_key` rows with a null in a key column or a key that occurs more than once, `row_count` one row when the count is outside `min` and `max`, and `sql` the rule's SELECT as written. Severity maps as for column rules (`error` as `error`, `warning` as `warn`, `none` writes no test). Any other table needs a `build.entrypoint`. `dpb generate` writes the model's dbt properties from the table file; nobody writes them by hand (ADR-0013, ADR-0015). A dbt model reads another data product's output port with `source('<port>', '<table>')`: for each input port that reads an output port, `dpb generate` writes a dbt source named after the port, pointing at the output port's schema and listing the producer's tables and columns from its table files, in `models/_sources.yml` of the reading data product (ADR-0018). A `ref()` into another data product's models is a read of a private table and fails the boundary check.

## What `dpb validate` enforces

- Every file matches the schema; unknown keys fail. Errors name the file and line, and all errors are reported at once.
- The port lists in `dataproduct.yaml` match the folders under `inputs/` and `outputs/`.
- Every derived name matches its naming template, and every name is snake_case.
- Port names and data product names are unique across the repo. Table names are unique within a data product.
- `kind` is a declared kind; `domain` is in the domain list when one is declared.
- An input port's `from` names an existing output port.
- A data product that reads an output port is among that port's readers.
- `needs` refers to existing tables and contains no cycle.
- An output port does not promise fresher data than its inputs deliver: its freshness is compared with the schedule of source input ports and the freshness of the output ports it reads.
- `executor` is `python` or `dbt`. Other executors arrive as plugins. A table built by dbt has no `entrypoint`, `params` or `needs`, and its model file exists in the data product's `models/` folder.
- Build code reads another data product only through an output port that it has an input port on and is a reader of. For dbt this is checked against the `ref()` and `source()` calls in the dbt manifest (ADR-0014). A model reads an output port through a generated `source()` (ADR-0018), so every `ref()` into another data product's models is a private read.
- The generated dbt properties, sources and singular data tests, and the `model-paths` and `test-paths` of `dbt_project.yml`, match the table files, and no hand-written dbt properties exist for a model that a table file builds (ADR-0013, ADR-0018, ADR-0019).

## Commands

| Command | What it does |
| --- | --- |
| `dpb new` | Scaffolds a data product folder that follows the conventions, with a stub function per table. Asks questions in a terminal; fails instead of asking with `--no-input`. `dpb new --from-dbt <path>` brings the models and properties of an existing dbt project into the new data product: it copies the models and writes a table file per model, and reports the data tests that map to no quality rule |
| `dpb validate` | Validates every data product. Meant for CI |
| `dpb list` | Shows all data products with kind, domain and owners |
| `dpb describe` | Prints one data product with all settings resolved, for humans or agents |
| `dpb config` | Prints the effective settings and where each one comes from |
| `dpb schema` | Prints the JSON Schema of the four kinds of file |
| `dpb generate` | Writes the orchestrator files and the warehouse SQL. Meant for CD |
| `dpb upgrade` | Rewrites files to the current schema version, keeping comments |

`validate`, `list`, `describe` and `config` take `--json`.

## What `dpb generate` writes

Generated files are build output of CD and are not committed, with one exception: the dbt properties and the `model-paths` and `test-paths` of `dbt_project.yml` are committed, because dbt reads them on every run.

**One Airflow 3 DAG per data product.** Each table gets a build task followed by an audit task. Task order follows `needs`. A data product with a source input port runs on that port's schedule. A data product that reads another data product's output port is triggered when that port is updated. The DAG ends with a task that applies the views and grants.

**Three runtimes.** `worker` calls the entrypoint on the Airflow worker. `docker` and `kubernetes` run it in a container from an image named in the settings (see ADR-0016).

**No connection management.** The views, grants and audits run on the orchestrator through a connection that already exists there; the settings only name it. Build code connects by itself: on the worker it can use that same connection, and in a container it reads what the team put in the container's environment.

**Views and grants for Postgres.** The executor builds every output table in the data product's private schema. An output port holds only generated views over those tables. A PII column shows its value to PII readers and NULL to everyone else. Readers are granted access to the views. The statements can be re-applied on every run, and removing a reader removes that reader's access.

**Access on DuckDB.** On DuckDB the warehouse enforces no access: it has no roles and no grants, so readers and PII readers are accepted and applied to nothing, and a PII column always shows NULL in the view, to everyone. DuckDB is meant for local development and tests. The same files then work on both warehouses (ADR-0021).

**Audit tasks.** Each quality rule becomes SQL that runs through the orchestrator's connection. A broken rule with severity `error` fails the run; `warning` reports and continues; `none` is skipped. In milestone 1 the audit runs after the table is built, so the data is already visible when a rule fails. Write-audit-publish closes that gap. For a table built by dbt, the quality rules run as dbt data tests during the dbt build instead.

**dbt properties.** For each table built by dbt, a properties file next to the model with its description, columns and types, quality rules as dbt data tests (table rules as generated singular tests, ADR-0019), an enforced dbt model contract, its alias and schema, and its data product's dbt group, plus a dbt source for each output port the data product reads (ADR-0018). `dpb generate` also keeps the `model-paths` and `test-paths` of the root `dbt_project.yml` in step with the data product folders.

## Settings and defaults

`executor`, `runtime`, the container image and the default `severity` can be set at four levels: root, data product, port and table. The nearest one wins. `orchestrator` can be set at root or data product level only, because one data product is one DAG.

Defaults ship inside the package in one file with the same shape as `datapatchbay.yaml`. The repo's file is merged over it: maps merge key by key, lists and single values replace.

## Plugins

Four extension points: orchestrator, executor, runtime and warehouse. Plugins are found through Python entry points. The built-in Airflow, Python, dbt, Postgres and DuckDB support is written against the same interfaces. The support for one technology lives in one folder, `src/datapatchbay/integrations/<technology>/` (ADR-0024). A plugin may declare its own settings section and naming templates (ADR-0025). The interface is not declared stable yet.

## Roadmap

1. **Milestone 1.** Schema version 1, all eight commands, Airflow 3 DAGs for the Python executor on three runtimes, Postgres views and grants, audit tasks with severity, the plugin interfaces.
2. **dbt executor.** Shipped: choose Python or dbt per data product or per table, dbt properties generated from the table files, models in the data product's folder, one `dbt build` task in the DAG. Still to come: the check that build code reads other data products only through their output ports (ADR-0014).
3. **Write-audit-publish.** Build into a staging table, audit, then publish. Configurable at all four levels.
4. **Semantic language.** datapatchbay's own format for measures, dimensions and joins, translated to other semantic model standards.
5. **Metadata and live freshness.** Data product metadata published either as tags at schema or table level, or as a separate data product with a configurable name. Freshness measured against real data.

Later, as someone needs them: more orchestrators, more warehouses, more port kinds (file, API, scheduled export), an MCP server.

## Out of scope

- Scheduling and orchestration
- A web UI or marketplace
- A metrics engine
- Catalog search across the company
- Connecting to the warehouse from `dpb`

## Open questions

- A data product with more than one source: one private input port or several?
- Is the thin semantic language enough, or will it grow into a second Cube?
- Which warehouses after Postgres and DuckDB?

## First milestone test

One two-person data team, one source, two data products running in production with `dpb validate` in CI. The test for the contract: a domain expert who does not write code can read a data product's files and confirm them. The test for the CLI: the engineer can run it without reading the docs.
