# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

The product is a CLI and has no UI. "web" covers its public surfaces: the GitHub repo, README, docs and identity assets.

## Users

Data and platform engineers on small and mid-size data teams (2 to 20 engineers). Typical cases are a central data team on a single warehouse that wants ownership and contracts without buying a catalog, or a company where a second or third team starts building on the same warehouse. Secondary readers are domain experts who don't write code but must be able to read a product file and confirm it, and AI agents that consume the CLI's `--json` output.

Not for large organisations with a governance department. A portal serves them better.

## Product Purpose

datapatchbay turns a data platform into a set of owned data products. Each product is a folder of YAML that states who owns it, what it reads, what it publishes, how fresh each output is, and who may read it. A single CLI (`dpb`) scaffolds those folders, validates them in CI and applies them to the warehouse.

It addresses four problems: tables nobody owns, everything being public, one concept carrying several names, and access managed by hand. The goal is to create a data product in five minutes.

Success for the first milestone: one two-person team, one source system and two products in production, with `dpb check` running in CI. A domain expert can read a product file, and an engineer can run the CLI without reading the docs.

## Positioning

Data mesh supplied the vocabulary and no implementation. datapatchbay is the implementation, kept small enough for a team of two. The real competitor is the internal cookiecutter every team builds and then abandons. datapatchbay adds to that scaffold the parts a cookiecutter lacks: check, list, deploy and an upgrade path.

The name comes from the patchbay behind a mixing console: every input and output has a labelled jack, and you route by declaring connections. Ports, inputs, outputs and connections are both the product's literal domain model and the source of its name.

## Operating Context

- Terminal, git and pull requests. Approvals happen in PRs.
- CI pipelines run `dpb check`.
- Orchestrators (Airflow, Dagster, cron) call `dpb deploy`.
- Warehouse: Postgres first.
- Existing dbt projects are wrapped, not modified.

## Capabilities and Constraints

- Commands: `new`, `check`, `list`, `describe`, `deploy`, `export`.
- One output port per schema. A port has a `kind` (`schema`, later `file`, `api`, `export`), a freshness promise, and an access policy (reader groups, PII columns).
- Inputs are declared at product level, inferred at table level, and opt-in at column level.
- A thin semantic layer (measures, dimensions, joins) is exported to Cube or dbt metrics.
- Built for agents: `--json` everywhere, YAML or JSON on stdin, non-interactive mode, and a published JSON schema.
- Python, distributed with uv. Apache 2.0.
- Out of scope: scheduling, a web UI or marketplace, a metrics engine, company-wide catalog search.
- Open: Python vs dbt executor order, the migration and upgrade command, how far the semantic format grows, warehouses after Postgres.

## Brand Commitments

- Name: **datapatchbay**. Short form "patchbay" is used in the repo. CLI alias: `dpb`. GitHub org: `datapatchbay`.
- The patchbay metaphor is binding: labelled jacks and declared connections.
- Voice: plain, direct, engineer-to-engineer, with no hype.

## Evidence on Hand

- Status: design stage, nothing released.
- No users, testimonials, benchmarks or logos exist yet. Do not invent any.
- No visual identity exists yet.

## Product Principles

1. Files and the CLI are the product, and conventions are the value.
2. The contract never names a technology. Executors are swappable.
3. Stay small and composable. Don't compete with schedulers, catalogs or portals.
4. Human-readable and agent-readable at the same time.
5. Five minutes to the first product.
