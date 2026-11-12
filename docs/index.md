# datapatchbay

**Data products as code.** Declare owners, ports and freshness in YAML, then scaffold, validate and generate from one lightweight CLI.

## The problem

Small and mid-size data teams hit the same four issues once more than one person or domain is involved:

- **Nobody owns a table.** When a number is wrong, there is no name to call.
- **Everything is public.** Consumers join straight into intermediate tables, so every refactor breaks a report.
- **The same concept has several names,** and each gets a different count.
- **Access is handled by hand,** so nobody can safely query the warehouse directly, and neither can an AI agent.

Data mesh gave teams the vocabulary for this but no implementation. The goal here is that creating a data product takes five minutes.

## What datapatchbay does

datapatchbay is a file-based CLI that turns a data platform into a set of owned data products. Each data product is a folder of YAML files. They state who owns it, what it reads, what it publishes, how fresh each output is, and who may read it. The CLI scaffolds those folders, validates them in CI, and generates the orchestrator and warehouse files that put them into effect.

If the term is new to you, read [What is a data product](data-products.md) first.

The name comes from the patchbay behind a mixing console. Every input and output has a labelled jack, and you route by declaring connections. The command is `dpb`, and the project is licensed under Apache 2.0.

## What it supports

| Part of the platform | Supported |
| --- | --- |
| Warehouse | Postgres. DuckDB for local development and tests, where no access is enforced |
| Orchestrator | Airflow 3, Dagster, or a generated script that needs no orchestrator |
| Build code | Python functions and dbt models, chosen per table |
| Where build code runs | On the orchestrator's worker. With Airflow, also in a Docker or Kubernetes container |

datapatchbay is not released yet. It is not on PyPI, so you install it from GitHub, and the plugin interface may still change. [Limits and guarantees](limits.md) lists what it does and does not do today, and [Why not just dbt](alternatives.md) says when another tool fits better.

## A first look

An output port is where a data product publishes data for others. It is a folder with a `port.yaml`, which states how fresh the data must be and who may read it:

```yaml
# dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/port.yaml
schema_version: 1
kind: schema
freshness: 24h
access:
  readers:
    - grp-shop-reporting
    - product: agg_order_turnaround
  pii_readers: [grp-shop-support]
```

Three commands take a data product from nothing to a DAG:

```console
$ dpb new --name jaffle_orders --kind source-aligned --owner "Jane Doe" --source jaffle_shop --no-input
$ dpb validate
ok: 1 data product(s) valid
$ dpb generate
```

`dpb new` scaffolds the folder. `dpb validate` checks every file and the rules across files, and is meant for CI. `dpb generate` writes an Airflow DAG that builds the tables, audits them, and applies the views and grants.

## Install

You need [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer:

```sh
uv tool install git+https://github.com/datapatchbay/patchbay
```

[Installation](installation.md) lists the other ways to install it, and what the orchestrator needs.

## Where to go next

New to datapatchbay
: Read [What is a data product](data-products.md), then follow the [tutorial](tutorial.md). It builds two data products from an empty folder, and runs one of them on your machine.

You evaluate it for your team
: [Why not just dbt](alternatives.md) compares it with dbt, a medallion architecture and other tools. [How it works](concepts.md) explains the model, and [Limits and guarantees](limits.md) lists what to expect in production.

You have a task
: The how-to guides cover one task each: [run without an orchestrator](howto/local.md), [validate in CI](howto/ci.md), [deploy the generated DAGs](howto/deploy.md), [give a reader access](howto/access.md), [build a table with dbt](howto/dbt.md), [import an existing dbt project](howto/import-dbt.md), [run build code in a container](howto/containers.md), [run on Dagster](howto/dagster.md) and [set up your editor](howto/editor.md). When a command fails, see [Troubleshooting](troubleshooting.md).

You look something up
: The reference describes [the commands](cli.md), [what `dpb validate` checks](validation.md), [what `dpb generate` writes](generated.md), [the four kinds of file](files.md), [the settings](settings.md), [the dbt support](dbt.md) and [the terms](glossary.md).

## Who it is for

- A central data team on a single platform that wants ownership and contracts without buying a catalog.
- A company where a second or third team starts building on the same warehouse.
- Teams of 2 to 20 engineers, usually with one monorepo.

## Principles

Lightweight
: Three dependencies: Pydantic, Typer and ruamel.yaml. Managed and distributed with uv.

`dpb` never connects to the warehouse
: It reads YAML and writes files. The orchestrator and the runtime do all the connecting.

Generated files stand alone
: They do not import datapatchbay. If someone deletes datapatchbay, the DAGs still run.

No scheduler
: The orchestrator schedules, and `dpb` generates what it runs.

CLI and files, no UI
: Approvals happen in pull requests.

Defaults for everything
: A team writes down only where it differs from the defaults.

Built for agents
: `--json` output, a published JSON Schema, and a mode that fails instead of prompting.

## Getting help

- Ask a question or report a bug in the [GitHub issues](https://github.com/datapatchbay/patchbay/issues).
- The source is at [github.com/datapatchbay/patchbay](https://github.com/datapatchbay/patchbay). [`examples/jaffle_shop`](https://github.com/datapatchbay/patchbay/tree/main/examples/jaffle_shop) is a finished repo with two data products.
- To change datapatchbay itself, see [Contributing](contributing.md).

```{toctree}
:hidden:
:caption: Getting started

data-products
installation
tutorial
```

```{toctree}
:hidden:
:caption: How-to guides

howto/local
howto/ci
howto/deploy
howto/access
howto/dbt
howto/import-dbt
howto/containers
howto/dagster
howto/editor
troubleshooting
```

```{toctree}
:hidden:
:caption: Reference

cli
validation
generated
files
settings
dbt
glossary
```

```{toctree}
:hidden:
:caption: Explanation

concepts
alternatives
limits
Design decisions <https://github.com/datapatchbay/patchbay/tree/main/docs/adr>
```

```{toctree}
:hidden:
:caption: Project

roadmap
plugins
contributing
GitHub <https://github.com/datapatchbay/patchbay>
```
