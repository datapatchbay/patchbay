# Roadmap

1. **Milestone 1.** Schema version 1, all eight commands, Airflow 3 DAGs for the Python executor on three runtimes, Postgres views and grants, audit tasks with severity, and the plugin interfaces.
2. **dbt executor.** Choose Python or dbt per data product or per table. dbt properties generated from the table files, models in the data product's folder, and the check that build code reads other data products only through their output ports. Uses the existing dbt profile for connections.
3. **Write-audit-publish.** Build into a staging table, audit it, then publish. Configurable at all four levels.
4. **Semantic language.** datapatchbay's own format for measures, dimensions and joins, translated to other semantic model standards.
5. **Metadata and live freshness.** Data product metadata published either as tags at schema or table level, or as a separate data product with a configurable name. Freshness measured against real data.

Later, as someone needs them:
- more orchestrators
- more warehouses
- more port kinds: file, API and scheduled export
- an MCP server

## Out of scope

- Scheduling and orchestration
- A web UI or marketplace
- A metrics engine
- Catalog search across the company
- Connecting to the warehouse from `dpb`

## Open questions

- A data product with more than one source: one private input port or several?
- How does a container runtime receive the entrypoint and its params?
- Are warehouse roles created by the generated SQL, or expected to exist?
- Is the thin semantic language enough, or will it grow into a second Cube?
- Which warehouses come after Postgres?
