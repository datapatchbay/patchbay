# datapatchbay

**Data products as code.** Declare owners, ports and freshness in YAML, then scaffold, validate and generate from one lightweight CLI.

datapatchbay is a file-based CLI that turns a data platform into a set of owned data products. Each data product is a folder of YAML files. They state who owns it, what it reads, what it publishes, how fresh each output is, and who may read it. The CLI scaffolds those folders, validates them in CI, and generates the orchestrator and warehouse files that put them into effect.

The name comes from the patchbay behind a mixing console. Every input and output has a labelled jack, and you route by declaring connections.

The command is `dpb`, and the project is licensed under Apache 2.0.

## A first look

An output port is a folder with a `port.yaml`. The file states how fresh the data is and who may read it:

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

You need [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer. datapatchbay is not on PyPI yet, so install it from GitHub:

```sh
uv tool install git+https://github.com/datapatchbay/patchbay
```

[Installation](installation.md) lists the other ways to install it, and what the orchestrator needs.

## Where to go next

New to datapatchbay
: Follow the [tutorial](tutorial.md). It builds two data products, from an empty folder to two generated DAGs.

You have a task
: The how-to guides cover one task each: [validate in CI](howto/ci.md), [deploy the generated DAGs](howto/deploy.md), [give a reader access](howto/access.md), [build a table with dbt](howto/dbt.md), [run build code in a container](howto/containers.md) and [set up your editor](howto/editor.md). When a command fails, see [Troubleshooting](troubleshooting.md).

You look something up
: The reference describes [the commands](cli.md), [the four kinds of file](files.md), [the settings and plugins](settings.md) and [the terms](glossary.md).

You want to know why
: [Data products](data-products.md) explains the idea behind datapatchbay and lists books to read. [How it works](concepts.md) explains the model. [Alternatives](alternatives.md) compares datapatchbay with other tools.

## The problem

Small and mid-size data teams hit the same four issues once more than one person or domain is involved:

- **Nobody owns a table.** When a number is wrong, there is no name to call.
- **Everything is public.** Consumers join straight into intermediate tables, so every refactor breaks a report.
- **The same concept has several names,** and each gets a different count.
- **Access is handled by hand,** so nobody can safely query the warehouse directly, and neither can an AI agent.

Data mesh gave teams the vocabulary for this but no implementation. The goal here is that creating a data product takes five minutes.

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

## First milestone test

One two-person data team, one source, and two data products running in production with `dpb validate` in CI.

- **The test for the contract:** a domain expert who does not write code can read a data product's files and confirm them.
- **The test for the CLI:** the engineer can run it without reading the docs.

## Getting help

- Ask a question or report a bug in the [GitHub issues](https://github.com/datapatchbay/patchbay/issues).
- The source is at [github.com/datapatchbay/patchbay](https://github.com/datapatchbay/patchbay). [`examples/jaffle_shop`](https://github.com/datapatchbay/patchbay/tree/main/examples/jaffle_shop) is a finished repo with two data products.
- To change datapatchbay itself, see [Contributing](contributing.md).

```{toctree}
:hidden:
:caption: Getting started

installation
tutorial
```

```{toctree}
:hidden:
:caption: How-to guides

howto/ci
howto/deploy
howto/local
howto/dagster
howto/access
howto/dbt
howto/containers
howto/editor
troubleshooting
```

```{toctree}
:hidden:
:caption: Reference

cli
files
settings
glossary
```

```{toctree}
:hidden:
:caption: Explanation

data-products
concepts
alternatives
Design decisions <https://github.com/datapatchbay/patchbay/tree/main/docs/adr>
```

```{toctree}
:hidden:
:caption: Project

roadmap
contributing
GitHub <https://github.com/datapatchbay/patchbay>
```
