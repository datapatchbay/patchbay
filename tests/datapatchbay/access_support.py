"""Constants and helpers shared by the unit tests and the integration tests of the Postgres access SQL."""

from pathlib import Path

from plan_helpers import plan_all

from datapatchbay.files.loading import load_repo
from datapatchbay.integrations.postgres.warehouse import PostgresWarehouse
from datapatchbay.plugins import DataProductPlan

PORT = "dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/port.yaml"
ORDERS = "dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/orders.yaml"

PORT_FILE = """\
schema_version: 1
kind: schema
freshness: 24h
access:
  readers:
    - grp-shop-reporting
    - product: agg_order_turnaround
  pii_readers: [grp-shop-support]
"""
ORDERS_FILE = """\
schema_version: 1
name: orders
columns:
  - name: order_id
    type: text
  - name: customer_id
    type: text
    pii: true
  - name: status
    type: text
build:
  entrypoint: src/orders.py:build
  needs: [ingested_orders]
"""


def plan_of(root: Path) -> DataProductPlan:
    loaded, problems = load_repo(root)
    assert problems == []
    return next(p for p in plan_all(loaded, root) if p.folder == "sa_jaffle_orders")


def apply_sql(root: Path) -> str:
    (task,) = PostgresWarehouse().apply_tasks(plan_of(root))
    return task.sql
