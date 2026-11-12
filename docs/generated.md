# What `dpb generate` writes

`dpb generate` writes one file per data product into the output folder. The file is named after the data product folder. What it holds depends on the `orchestrator` setting:

| Orchestrator | The file | Described in |
| --- | --- | --- |
| `airflow` (default) | An Airflow 3 DAG | This page |
| `dagster` | A Python module with Dagster definitions | [Run on Dagster](howto/dagster.md) |
| `local` | A Python script that runs the data product once | [Run a data product without an orchestrator](howto/local.md) |

Whatever the orchestrator, the file holds the same four parts: the build of each table, the audit of its quality rules, the SQL that makes the output ports, and a signal that the output ports were updated. The generated files do not import datapatchbay, so the orchestrator needs neither datapatchbay nor its dependencies installed.

For tables built by dbt, `dpb generate` also writes dbt files into the repo. See the [dbt reference](dbt.md#generated-dbt-files). [The `dpb` CLI](cli.md#dpb-generate) describes the command itself.

## The Airflow DAG

There is one DAG per data product, named after the data product folder, with the tag `datapatchbay`.

Tasks
: Each table gets a build task, `build_<table>`, followed by an audit task, `audit_<table>`, when it has quality rules that are not `none`. Task order follows `needs`, and a table that needs another waits for that table's audit. After the last table comes `apply_access`, which applies the views and grants. The DAG ends with `publish_outputs`.

Schedule
: A data product with a source input port runs on that port's schedule. All its source input ports must share one schedule. A data product that reads another data product's output port is triggered when that port is updated. With both, it runs on the schedule once the ports are updated.

Output ports
: Each output port is an Airflow asset named after the port. `publish_outputs` marks the output ports as updated when the DAG succeeds.

Tables built by dbt
: They share one task, `build_dbt`, that runs `dbt build` on the worker. See [dbt on the worker](dbt.md#dbt-on-the-worker).

## Build tasks and runtimes

The runtime of a table says where its build function runs. Tables with different runtimes can sit in one DAG.

`worker`
: The task loads the entrypoint file from the data product folder and calls the function with the table's `params`, on the Airflow worker. It finds the folder from the DAG file's own location, so the output folder and the data product folders must keep their relative places when deployed. Deploying the whole repo does that. See [Deploy the generated DAGs](howto/deploy.md).

`docker` and `kubernetes`
: The task runs the function in a container from the table's resolved `image`, as a `DockerOperator` or `KubernetesPodOperator`. DAG files that use them need `apache-airflow-providers-docker` or `apache-airflow-providers-cncf-kubernetes` on Airflow. The container runs `python -c` with a short loader, the entrypoint file, the function and the `params` as JSON. So the image needs `python`, the build code, and the data product folder as its working directory ([ADR-0016](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0016-containers-get-the-entrypoint-as-arguments-to-python.md)). The `container` setting is added to the task as written, which is where a team supplies environment variables or secrets. See [Run build code in a container](howto/containers.md).

The `params` must be plain YAML values: a date has to be quoted.

## Audit tasks

The audit task of a table runs every quality rule as a query that counts the rows that break it. The audit code is part of the generated file.

- A broken rule with severity `error` fails the task. The message names the rule, the table and the column, and all broken `error` rules are named together.
- A broken rule with severity `warning` is written to the task log, and the task succeeds.
- A rule with severity `none` is skipped. A table whose rules all have severity `none` gets no audit task.
- A bare rule name takes the default severity, which cascades from `datapatchbay.yaml` down to the table.

Tables are audited in their data product's private schema. `accepted_values` compares values with the column's type, so write numbers and booleans unquoted for numeric and boolean columns. A `sql` rule's SELECT may end in a semicolon.

For a table built by dbt, the rules run as dbt data tests during the dbt build instead, and the table gets no audit task.

## Views and grants

The `apply_access` task makes each output port real. Build code writes every output table to the data product's private schema. An output port holds only generated views over those tables, one view per table, with the columns of the table file. A data product without output ports gets no `apply_access` task.

On Postgres
: A PII column shows its value to PII readers and NULL to everyone else, and readers are granted access to the views. The statements can be re-applied on every run, and removing a reader removes that reader's access. The roles must already exist in the warehouse: the SQL grants to them and never creates them ([ADR-0017](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0017-warehouse-roles-are-expected-to-exist.md)). The views are dropped and created again on every run, so a view in another schema that depends on an output port's view blocks the apply.

On DuckDB
: DuckDB has no roles and no grants, so readers and PII readers are accepted and applied to nothing, and a PII column shows NULL in the view, to everyone. The schema of each output port is dropped and created again on every apply. DuckDB is meant for local development and tests. The same files work on both warehouses, so a team can develop on DuckDB and deploy on Postgres by changing the `warehouse` setting ([ADR-0021](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0021-duckdb-enforces-no-access.md)).

## Connections

`dpb` manages no connection. The views, grants and audits run on the orchestrator, through a connection that already exists there. The `connection` setting only names it, `warehouse` by default. Build code connects by itself.

### The Airflow connection for DuckDB

With `warehouse: duckdb`, install the official `apache-airflow-providers-duckdb` package on the workers and create a connection of type `duckdb` with the id that the `connection` setting names. Its **Host** field is the path of the DuckDB file, for example `/data/shop.duckdb`. With no path, the hook opens an in-memory database that is gone when the task ends, so the views would never persist. As an environment variable:

```sh
AIRFLOW_CONN_WAREHOUSE='{"conn_type": "duckdb", "host": "/data/shop.duckdb"}'
```

DuckDB is a file that one process writes at a time. The file must be on a path that every worker running the DAG and the build code can reach, and the build code opens the same file by itself. So let the DAG run one run at a time.
