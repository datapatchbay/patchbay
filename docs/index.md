# datapatchbay

**Data products as code.** Declare owners, ports and freshness in YAML, then scaffold, validate and generate from one lightweight CLI.

datapatchbay is a file-based CLI that turns a data platform into a set of owned data products. Each data product is a folder of YAML files. They state who owns it, what it reads, what it publishes, how fresh each output is, and who may read it. The CLI scaffolds those folders, validates them in CI, and generates the orchestrator and warehouse files that put them into effect.

The name comes from the patchbay behind a mixing console. Every input and output has a labelled jack, and you route by declaring connections.

The command is `dpb`, and the project is licensed under Apache 2.0.

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

```{toctree}
:hidden:
:caption: Guide

concepts
files
cli
settings
roadmap
```

```{toctree}
:hidden:
:caption: Background

alternatives
glossary
```
