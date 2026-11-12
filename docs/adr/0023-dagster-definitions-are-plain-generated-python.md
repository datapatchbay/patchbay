# Dagster definitions are plain generated Python, with output ports as assets

The `dagster` orchestrator writes one Python module per data product. It defines an asset for each table and each output port, asset checks for the quality rules, a job, schedules and sensors, and ends with `defs`, which a team merges with the `defs` of its other data products. The module imports only `dagster` and the standard library, like the Airflow DAG file (ADR-0001). It runs the warehouse's SQL through a resource that the team binds under the key of the `connection` setting; the resource has a `get_connection()` method that yields a DB-API connection which commits by itself. We chose this so that a team on Dagster gets the same generated files and the same contract as a team on Airflow, and so that the data products depend on each other by asset key.

An output port is an asset with the key `[<port>]`. It depends on every table of its data product, so it materializes after the tables and their blocking checks. A data product that reads a port lists it as a dependency of its first tables, and has a sensor on that asset that runs the job. The job selects the group of the data product and has a schedule for the cron of its source input ports. A rule with severity `error` is a blocking check, so a broken rule stops the assets downstream, as it stops the publish task in Airflow (ADR-0010).

## Considered options

- **Declarative automation instead of a job with a schedule and sensors.** Rejected: it decides what to build from the state of the assets, so a run depends on what happened before, and the cron of a source port would have to be expressed as a condition. A job that builds the whole group is one run with one outcome, the same unit as an Airflow DAG run, and the schedule is the cron of the files.
- **A Dagster component that reads the YAML when Dagster loads.** Rejected: it imports datapatchbay and Pydantic into the Dagster environment, which ADR-0001 rejects for the Airflow DAG files too. The generated module keeps working when datapatchbay is removed.
- **The output ports as a side effect of the last table, not as assets.** Rejected: another data product then has nothing to depend on except a table that is private to its producer.
- **A connection setting that is a connection string, or `dpb` opening the connection.** Rejected: `dpb` holds no credentials (ADR-0001). The team binds a resource, and the `connection` setting only names its key.
- **Wait for dbt's own Dagster integration for the dbt tables.** Rejected for now: it needs `dagster-dbt` and the dbt manifest in the Dagster environment. The tables built by dbt are one multi-asset that runs `dbt build`, as in the Airflow DAG.

## Consequences

- Only the `worker` runtime renders a build for Dagster. The `docker` and `kubernetes` runtimes raise `UnsupportedCombinationError` for it until they are written for Dagster.
- The names in a module are prefixed with the data product's folder, because all `defs` end up in one code location. A folder, table or port name that is not letters, digits and underscores is refused, because Dagster does not accept it for a group, job, schedule or sensor.
- A sensor starts a run when any port that the data product reads is materialized. An Airflow DAG waits for all of them. Different crons on the source ports are not an error: one schedule has all of them.
- Schedules and sensors are running by default.
- The module cannot start without a resource under the key of the `connection` setting, when it has a quality rule or an apply task. Dagster reports the missing key when it loads the definitions.
- A broken rule is reported with its table and column like in Airflow (ADR-0010), but each rule shows on its own in Dagster, and its violation count is in the metadata.
