"""A small repo for the `local` orchestrator tests, and a way to run its generated scripts for real on DuckDB."""

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import duckdb

from datapatchbay.pipeline.generate import generate_repo

SETTINGS = "schema_version: 1\norchestrator: local\nwarehouse: duckdb\nruntime: worker\n"

SA = "dataproducts/sa_shop_orders"
AGG = "dataproducts/agg_order_totals"

BUILD_RAW = """\
import os

import duckdb


def build():
    connection = duckdb.connect(os.environ["SHOP_DB"])
    connection.execute("CREATE SCHEMA IF NOT EXISTS sa_shop_orders_private")
    connection.execute(
        "CREATE OR REPLACE TABLE sa_shop_orders_private.raw_orders AS SELECT * FROM range(1, 4) t(order_id)"
    )
    connection.close()
"""

BUILD_ORDERS = """\
import os

import duckdb


def build():
    connection = duckdb.connect(os.environ["SHOP_DB"])
    connection.execute(
        "CREATE OR REPLACE TABLE sa_shop_orders_private.orders AS "
        "SELECT order_id FROM sa_shop_orders_private.raw_orders"
    )
    connection.close()
"""

BUILD_TOTALS = """\
import os

import duckdb


def build():
    connection = duckdb.connect(os.environ["SHOP_DB"])
    connection.execute("CREATE SCHEMA IF NOT EXISTS agg_order_totals_private")
    connection.execute(
        "CREATE OR REPLACE TABLE agg_order_totals_private.totals AS "
        "SELECT count(*)::INTEGER AS n FROM sa_shop_orders.orders"
    )
    connection.close()
"""

FILES = {
    "datapatchbay.yaml": SETTINGS,
    f"{SA}/dataproduct.yaml": (
        "schema_version: 1\nname: shop_orders\nkind: source-aligned\nowner: Jane\n"
        "inputs: [sa_shop_orders_private]\noutputs: [sa_shop_orders]\n"
    ),
    f"{SA}/inputs/sa_shop_orders_private/port.yaml": (
        'schema_version: 1\nkind: schema\nsource: shop\nschedule: "0 5 * * *"\n'
    ),
    f"{SA}/inputs/sa_shop_orders_private/raw_orders.yaml": (
        "schema_version: 1\nname: raw_orders\ncolumns:\n  - name: order_id\n    type: integer\n"
        "build:\n  entrypoint: src/raw.py:build\n"
    ),
    f"{SA}/outputs/sa_shop_orders/port.yaml": (
        "schema_version: 1\nkind: schema\naccess:\n  readers:\n    - product: agg_order_totals\n"
    ),
    f"{SA}/outputs/sa_shop_orders/orders.yaml": (
        "schema_version: 1\nname: orders\ncolumns:\n  - name: order_id\n    type: integer\n    rules: [not_null]\n"
        "build:\n  entrypoint: src/orders.py:build\n  needs: [raw_orders]\n"
    ),
    f"{SA}/src/raw.py": BUILD_RAW,
    f"{SA}/src/orders.py": BUILD_ORDERS,
    f"{AGG}/dataproduct.yaml": (
        "schema_version: 1\nname: order_totals\nkind: aggregate\nowner: Ann\n"
        "inputs: [sa_shop_orders]\noutputs: [agg_order_totals]\n"
    ),
    f"{AGG}/inputs/sa_shop_orders/port.yaml": "schema_version: 1\nfrom: sa_shop_orders\n",
    f"{AGG}/outputs/agg_order_totals/port.yaml": "schema_version: 1\nkind: table\n",
    f"{AGG}/outputs/agg_order_totals/totals.yaml": (
        "schema_version: 1\nname: totals\ncolumns:\n  - name: n\n    type: integer\n"
        "build:\n  entrypoint: src/totals.py:build\n"
    ),
    f"{AGG}/src/totals.py": BUILD_TOTALS,
}


def write_repo(root: Path, **overrides: str) -> Path:
    """Write the shop repo into `root`: `sa_shop_orders`, and `agg_order_totals`, which reads it. Files in `overrides`
    (keyed by path relative to the repo) replace the default content."""
    for relative, text in {**FILES, **overrides}.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def generate(root: Path) -> Path:
    """Run `dpb generate` on the repo and return the folder with the scripts."""
    result = generate_repo(root)
    assert result.report.ok, result.report
    return root / "generated"


def run_script(
    script: Path,
    *arguments: str,
    database: Path | None = None,
    url: str | None = None,
    variable: str = "DPB_CONNECTION_WAREHOUSE",
    without_connection: bool = False,
    extra_environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a generated script in a new process, like cron would.

    The environment has none of the developer's own `DPB_CONNECTION_*` variables. With a `database`, the build
    functions find it in `SHOP_DB` and `variable` holds `duckdb:<database>`, unless `url` says otherwise or
    `without_connection` leaves the variable out.
    """
    environment = {key: value for key, value in os.environ.items() if not key.startswith("DPB_CONNECTION_")}
    if database is not None:
        environment["SHOP_DB"] = str(database)
    if not without_connection and (url is not None or database is not None):
        environment[variable] = url if url is not None else f"duckdb:{database}"
    environment.update(extra_environment or {})
    return subprocess.run(
        [sys.executable, str(script), *arguments], capture_output=True, text=True, env=environment, check=False
    )


def query(database: Path, sql: str) -> list[tuple]:
    """Run a query on the DuckDB file and return its rows."""
    connection = duckdb.connect(str(database))
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()
