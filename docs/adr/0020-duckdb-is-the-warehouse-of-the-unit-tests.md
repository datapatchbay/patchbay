# DuckDB is the warehouse of the unit tests

DuckDB is a second built-in warehouse, registered through the same entry point as Postgres (ADR-0009). It runs inside the test process, with no server, so the unit tests run the SQL that `dpb` generates against DuckDB and CI needs no services. A test that needs a Postgres server, Airflow or dbt is an integration test: it runs on a developer's machine in Docker and never in CI. We chose this because starting Postgres and installing Airflow on every pull request was too expensive, while most of what those jobs checked, such as a quality rule counting the right rows or a view showing the right columns, can be checked in any warehouse that runs the SQL.

`duckdb` is a development dependency only. The package still ships no database driver, and `dpb` still never connects to a warehouse (ADR-0001, ADR-0004). The default warehouse stays Postgres.

## Considered options

- **Keep the Postgres, Airflow and dbt jobs in CI.** Rejected: too expensive to run on every pull request.
- **Unit tests that only compare the generated SQL as text.** Rejected: the text says nothing about what the SQL does. Generated SQL can only be checked by running it.
- **SQLite as the warehouse of the unit tests.** Rejected: it has no schemas, so a private schema with output ports as views over it (ADR-0002) cannot be expressed, and nobody would use it as a warehouse. DuckDB is a warehouse that teams do use, so its plugin is a feature and not test code.

## Consequences

- CI runs the unit tests on every supported Python, ty and ruff, and nothing else. `uv run pytest` runs the same unit tests, with no network and no server.
- The integration tests are started with one command and need only Docker on the developer's machine. They cover what DuckDB cannot: the Postgres SQL on a real Postgres, the generated DAGs loaded and run in Airflow, and the generated dbt properties parsed by dbt.
- CI no longer checks a change to the Postgres SQL, to the generated DAGs or to the dbt properties against the real tool. Whoever changes one of those runs the integration tests before pushing.
- DuckDB has no roles and no grants. Granting to readers and masking by role (ADR-0007, ADR-0017) can only be checked on Postgres, so those checks are integration tests. What readers and PII readers mean on DuckDB is a separate decision, made in ADR-0021.
- The orchestrator reaches DuckDB through its own connection, as it does for any warehouse (ADR-0001).
- DuckDB is the second implementation of the warehouse extension point, so it tests that interface the way the dbt executor tests the executor interface (ADR-0009).
