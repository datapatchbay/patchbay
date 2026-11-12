# dpb never connects to the warehouse

`dpb` reads YAML and writes files: Airflow DAG files and SQL for views and grants. It holds no credentials and ships no database driver. The orchestrator and the runtime do all the connecting, so the generated DAG ends with a task that runs the view and grant SQL through the orchestrator's own connection. We chose this to keep the tool lightweight and to avoid a second place where warehouse credentials live.

The generated DAG files are static and do not import datapatchbay, so the orchestrator needs neither datapatchbay nor its dependencies installed, and the DAGs keep running if datapatchbay is removed.

## Considered options

- **A `dpb deploy` that connects and applies.** Rejected: it adds a driver per warehouse and credential handling to the tool, and duplicates connections the orchestrator already has.
- **A dynamic loader that reads the YAML when the orchestrator parses its DAG folder.** Rejected: it puts datapatchbay and Pydantic into the orchestrator's environment.

## Consequences

- `dpb` manages no connections. The settings name a connection that already exists on the orchestrator, and `dpb` does not create it, store it or pass it on.
- The orchestrator must have a connection to the warehouse, because the views, grants and audits run there. This also holds when builds run in containers: the build code reads its credentials from the container's environment, which the team provides.
- A change to access takes effect on the next run of the data product's DAG, or on a manual trigger, not at merge time.
- `dpb validate` can only test what the files state. Anything that needs real data, such as measured freshness or quality rules, has to run as a generated task.
