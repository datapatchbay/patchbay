# Run a data product without Airflow

With `orchestrator: local`, `dpb generate` writes one Python script per data product. The script builds the data product once: it runs the builds, the audits and then the SQL of the warehouse. Use it to run a data product by hand, from cron or in CI, with no orchestrator.

The script does the connecting, not `dpb` ([ADR-0001](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0001-dpb-never-connects-to-the-warehouse.md)). It imports only the standard library and the warehouse driver, never datapatchbay.

## 1. Set the orchestrator

```yaml
# datapatchbay.yaml
orchestrator: local
warehouse: duckdb
runtime: worker
```

The `orchestrator` setting cascades like the others, so you can also set it in one `dataproduct.yaml`. Then run `dpb generate`. The script `<folder>.py` is written next to the Airflow DAG files, in the `output_dir` folder.

Only `runtime: worker` works. The `docker` and `kubernetes` runtimes make `dpb generate` fail for this orchestrator. The build code runs in the process of the script, so the script needs the same Python packages as the build code.

## 2. Set the connection

The script reads the URL of the warehouse from an environment variable. The `connection` setting (default `warehouse`) names it: the variable is `DPB_CONNECTION_` and the name in upper case, with every character outside `A-Z` and `0-9` replaced by `_`. The default is `DPB_CONNECTION_WAREHOUSE`; `connection: shop-db` gives `DPB_CONNECTION_SHOP_DB`.

The URL has one of these forms:

- `duckdb:<path>` or `duckdb:///<absolute path>`: a DuckDB file. A relative path starts at the folder you run the script from.
- `postgresql://<user>:<password>@<host>/<database>` or `postgres://...`: a Postgres database.

```sh
export DPB_CONNECTION_WAREHOUSE=duckdb:/data/warehouse.duckdb
```

The script imports the driver, `duckdb` or `psycopg`, only when it connects, so you install the one you use. A missing variable or any other URL stops the script with a message that names the variable and these forms. The script opens a connection for each audit and each SQL step, and closes it afterwards.

Your build code reads its own credentials, as it does under Airflow. The script passes it nothing.

## 3. Run it

```sh
python generated/sa_jaffle_orders.py
```

The script runs the steps in order and stops at the first one that fails, with a non-zero exit code:

1. For each table, in order: its build, then its audit.
2. When dbt builds tables, one `dbt build` for all of them. It needs the `dbt` command on the path and a dbt profile. See [Build a table with dbt](dbt.md).
3. The SQL of the warehouse: the views of the output ports and the grants.

It logs one line per step to stderr, for example `sa_jaffle_orders: build_ingested_orders`. A broken rule with severity `warning` is logged. A broken rule with severity `error` fails the script, and the SQL of the warehouse does not run.

## 4. Run the data products it reads

A data product reads output ports of other data products. To run those first, add `--upstream`:

```sh
python generated/agg_order_turnaround.py --upstream
```

The script looks at the other `*.py` files in its own folder and keeps those that are local scripts. It then runs every data product it reads, directly or indirectly, once each and in dependency order, before itself. The files are read, not imported. A port that no script in the folder produces is logged as a warning and skipped: it may belong to a data product on another orchestrator. Data products that read each other in a cycle are an error.

## 5. Schedule it

The script does not schedule itself. Its top has a comment with the schedule of each source input port, for example:

```python
# This script does not schedule itself. The source input ports deliver data at:
#   0 5 * * *  sa_jaffle_orders_private
```

Use it for a crontab line. The environment variable must be set in the line, because cron starts with an empty environment:

```cron
0 5 * * * DPB_CONNECTION_WAREHOUSE=duckdb:/data/warehouse.duckdb /usr/bin/python3 /srv/repo/generated/sa_jaffle_orders.py
```

Regenerate with `dpb generate` after a change to the files. The script holds no state between runs, so you can run it again at any time.
