# Run on Dagster

With `orchestrator: dagster`, `dpb generate` writes one Python module per data product instead of an Airflow DAG file. The module defines Dagster assets, asset checks, a job, schedules and sensors. `dpb` runs nothing and connects to nothing: Dagster runs the module, with its own connection to the warehouse.

This guide sets up Dagster for two data products, `sa_jaffle_orders` and `agg_order_turnaround`, which reads the output port of the first.

## 1. Set the orchestrator

Set it in `datapatchbay.yaml` for every data product, or in one `dataproduct.yaml`:

```yaml
orchestrator: dagster
```

Only the `worker` runtime works with Dagster for now. The build function runs in the Dagster process that runs the step, in the environment of that process. `dpb generate` fails for a table on the `docker` or `kubernetes` runtime.

Run `dpb generate`. The module of a data product is `<folder>.py` in the output folder, the same place and name as the Airflow DAG file. It imports `dagster` and the standard library, never datapatchbay.

## 2. What is generated

| In the files | In Dagster |
| --- | --- |
| A table built by a Python function | An asset with the key `[<data product>, <table>]`, in the group `<data product>`. Its owner is in the metadata. |
| `needs` of a table | The asset depends on the assets of the tables in `needs`. A table without `needs` depends on the output port assets that the data product reads. |
| The quality rules of a table | An asset check on the table's asset, with one result for each rule. |
| The output ports | One asset for each output port, with the key `[<port>]`, in the same group. It depends on every table. It applies the views and grants of the warehouse. |
| The data product | A job named after the folder. It builds the whole group. |
| The `schedule` of the source input ports | A schedule on the job, in UTC, running by default. |
| An input port that reads another data product's output port | A sensor that runs the job when that port is materialized, running by default. |

The names are prefixed with the folder of the data product, so the definitions of all data products can be merged into one code location. The job is `sa_jaffle_orders`, the schedule `sa_jaffle_orders__schedule` and a sensor `agg_order_turnaround__on_sa_jaffle_orders`.

### Quality rules

A rule with severity `error` is a blocking check: when it is broken, the run fails and the assets downstream of the table do not materialize, so the output port is not updated. A rule with severity `warning` fails its check with Dagster's `WARN` severity and the run goes on. Each result has the number of violations in its metadata. A rule with severity `none` is not generated.

As in the Airflow DAG, the table is already built when its rules run. See [Limits and guarantees](../limits.md#quality-rules). Check names are unique for a table: a second rule with the same name on the same column gets `_2` after its name.

### Tables built by dbt

The tables of a data product that the `dbt` executor builds are one multi-asset, built by one `dbt build` after the Python tables. The `dbt` command must be on the path where Dagster runs the step, and the dbt project and profile are found as the `dbt` settings say. A Python table cannot need a dbt table, and the dbt tables of a data product must have the same runtime. `dpb generate` refuses both, as it does for Airflow.

## 3. Write the definitions file

Your team owns one file that merges the `defs` of all data products and binds the warehouse resource. Put it where Dagster can import the output folder, for example in the repo root:

```python
# definitions.py
import os

import dagster as dg
from dagster_duckdb import DuckDBResource

from generated import agg_order_turnaround, sa_jaffle_orders

defs = dg.Definitions.merge(
    sa_jaffle_orders.defs,
    agg_order_turnaround.defs,
    dg.Definitions(resources={"warehouse": DuckDBResource(database=os.environ["WAREHOUSE_DB"])}),
)
```

Check it, then start Dagster with the repo root as the working directory:

```sh
dagster definitions validate -f definitions.py -d .
dagster dev -f definitions.py -d .
```

`dagster` and `dagster-duckdb` are packages of your Dagster environment, not of `dpb`. Generate in CD before you deploy, as in [Deploy the generated DAGs](deploy.md). The module finds the data product folder relative to its own location, so deploy the repo with the output folder in it.

## 4. Provide the warehouse resource

Only the assets and checks that run SQL need the resource: the quality rules and the output ports. Its key is the `connection` setting, `warehouse` by default. Change the setting when your resource has another key.

The resource needs one method, `get_connection()`. It is a context manager that yields a DB-API connection: one with `cursor()`, and a cursor with `execute()` and `fetchone()`. The connection must commit by itself, because the generated SQL can hold its own `BEGIN` and `COMMIT`: use autocommit, or commit when the context exits.

`DuckDBResource` from `dagster-duckdb` fits, as in the example above. For Postgres, write the resource around `psycopg`:

```python
from contextlib import contextmanager

import dagster as dg
import psycopg


class PostgresResource(dg.ConfigurableResource):
    url: str

    @contextmanager
    def get_connection(self):
        with psycopg.connect(self.url, autocommit=True) as connection:
            yield connection


warehouse = dg.Definitions(resources={"warehouse": PostgresResource(url=dg.EnvVar("WAREHOUSE_URL"))})
```

Merge `warehouse` into the definitions file in place of the `DuckDBResource` one. The build functions read their own credentials from the environment of the Dagster process, as they do on Airflow.

## 5. Schedules and sensors

- The schedule and the sensors are running by default, so they start as soon as the code location is loaded. Turn one off in the Dagster UI if you do not want it.
- The schedule uses the `schedule` of the source input ports. When the ports have different crons, the schedule has all of them. Airflow refuses this. A data product without a source input port has no schedule.
- A data product that reads output ports of other data products has one sensor for each of them. The job runs when **any** of those ports is materialized. An Airflow DAG waits until **all** of them were updated. If your data product needs data from two upstream data products to be fresh, a run that starts after the first one builds from a mix of old and new data.
- The sensor runs the job once for each run of the upstream data product, and the upstream job must be run by the same Dagster instance.

## Limits

- Only the `worker` runtime.
- The quality rules and the views run after the table is built, so a failed rule stops the run but the data is already in the private table. See [Limits and guarantees](../limits.md#quality-rules).
- `dpb validate` does not load the generated modules. Check them with `dagster definitions validate`.
