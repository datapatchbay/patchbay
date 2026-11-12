# Design decisions

## CLI and files, no UI

The users are engineers, and the product is the set of conventions. Approvals happen in pull requests, which every team already has.

## The contract never names a technology

Product and table YAML contain no Python paths, dbt selectors or connection strings. Executors read the contract. How a product runs lives in a separate runner section that you can swap out.

## No scheduler

Airflow, Dagster or cron call `dpb deploy`. Competing with them would double the scope and lose.

## Wrap dbt, do not plug into it

A standalone CLI reads the existing dbt profiles and manifest. If someone deletes datapatchbay, their dbt project still runs.

## Plain Python executor first, dbt second

The first real deployment runs Python pipelines, so that executor ships first. This is the riskiest call in the design and may flip.

## One output port per schema

The tables inside the schema are the contract. A port has a `kind`: `schema` by default, later `file`, `api` and `export` for scheduled mails. A different way of delivering the data is a different port on the same product.

## Freshness belongs to the port and is a promise

"Fresh within 24 hours" is checked against the latest timestamp. A weekly mail export and a daily schema can sit on the same product, each with its own promise.

## Input ports at three levels

Inputs are declared by hand at product level, inferred from the code at table level, and opt-in at column level for consumers who want protection against a dropped column. Row filters are access control and sit on the output port.

## Access policy on the output port

The port names the reader groups and the PII columns. `dpb deploy` generates roles, grants and masked views from it. BI apps are listed as consumers at the app level, since individual reports change weekly.

## A thin semantic layer

Measures, dimensions and joins per table, exported to Cube or dbt metrics. Owning a small format and exporting from it is cheaper than following another project's roadmap.

## Built for agents from day one

Every command has `--json` output, takes YAML or JSON on standard input, and has a non-interactive mode that fails instead of prompting. A published JSON schema lets an agent validate before it writes. An MCP server comes later, if the CLI turns out to be too little.

## Python, distributed with uv

Data engineers read and contribute Python. Pydantic, Typer and psycopg cover validation, the CLI and Postgres.

## Out of scope

- Scheduling and orchestration
- A web UI or marketplace
- A metrics engine
- Catalog search across the company

## Open questions

- Does the plain Python executor stay first once the first deployment adopts dbt?
- How do existing products migrate when the conventions change? An upgrade command is planned but not designed yet.
- Is the thin semantic format enough, or will it grow into a second Cube?
- Which warehouses come after Postgres?
