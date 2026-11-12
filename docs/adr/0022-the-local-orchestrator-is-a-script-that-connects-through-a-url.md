# The local orchestrator is a generated script that connects through a URL in an environment variable

The `local` orchestrator makes `dpb generate` write one standalone Python script per data product, next to the Airflow DAG files. Running the script builds the data product once: the builds, the audits, then the SQL of the warehouse, stopping at the first failure. It gives a way to run a data product with no Airflow, by hand, from cron or in CI. The script imports only the standard library at import time, never datapatchbay, and does the connecting itself (ADR-0001). It finds the warehouse in an environment variable whose name comes from the `connection` setting, `DPB_CONNECTION_` and the name in upper case, with every other character replaced by `_`. The value is a URL: `duckdb:<path>`, `duckdb:///<absolute path>`, `postgresql://...` or `postgres://...`. The script imports the driver only when it connects. We chose this because the script has to reach a warehouse without an orchestrator that holds the connection, and a URL in the environment is the one form that cron, CI and a shell all provide.

The script does not schedule itself. It states the schedule of the source input ports in a comment, so whoever writes the crontab line can see it. It defines the plain constants `ORCHESTRATOR`, `DATAPRODUCT`, `READS` and `OUTPUTS`, which other scripts read with `ast` without importing it. With `--upstream` it first runs, once each and in dependency order, the local scripts in its own folder that produce the ports it reads.

## Considered options

- **A `dpb run` command that connects and runs.** Rejected: `dpb` would open connections and hold drivers and credentials, which breaks ADR-0001 and ADR-0004.
- **One file that runs every data product.** Rejected: one data product generates one file, and two data products may not generate the same file, so a shared file has no owner and breaks the way `dpb generate` removes stale files.
- **Real cron scheduling in the orchestrator**, such as a long-running process. Out of scope: cron and CI already schedule, and a scheduler is what Airflow is for.
- **A connection file or one environment variable per field** (host, user, password). Rejected: a URL fits in one variable, which is what a secret store hands out, and the same form works for DuckDB and Postgres.

## Consequences

- Only the `worker` runtime works with `local`. The `docker` and `kubernetes` runtimes refuse it when `dpb generate` runs, because they render Airflow operators. Build code runs in the process of the script and reads its own credentials, as it does under Airflow.
- The team installs the driver of the warehouse it uses, `duckdb` or `psycopg`, next to the build code's dependencies. `dpb` ships neither.
- Tables built by dbt run in one `dbt build` after the Python tables, as in Airflow, with the same refusals. It needs the `dbt` command.
- A read port that no local script in the folder produces is logged and skipped, because it may belong to a data product on another orchestrator. A cycle between local scripts is an error.
- The script opens a connection for each audit and each SQL step and closes it after. A build function that opens the same DuckDB file therefore never competes with the script for it.
- The orchestrator is the second implementation of its extension point (ADR-0009). Its audit code is shared with the Airflow DAG (ADR-0010), so the same rule gives the same message in both.
