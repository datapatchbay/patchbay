"""Constants and helpers shared by the unit tests and the integration tests of the Postgres access SQL."""

from pathlib import Path

from datapatchbay.builtin.postgres import PostgresWarehouse
from datapatchbay.loading import load_repo
from datapatchbay.planning import plan_dataproducts
from datapatchbay.plugins import DataProductPlan
from datapatchbay.settings import load_settings

PORT = "dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/port.yaml"
ORDERS = "dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/orders.yaml"

PORT_FILE = """\
schema_version: 1
kind: schema
freshness: 24h
access:
  readers:
    - grp-lab-reporting
    - product: agg_lab_turnaround
  pii_readers: [grp-lab-doctors]
"""
ORDERS_FILE = """\
schema_version: 1
name: orders
columns:
  - name: order_id
    type: text
  - name: patient_id
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
    return next(p for p in plan_dataproducts(loaded, load_settings(root)) if p.folder == "sa_ilab_orders")


def apply_sql(root: Path) -> str:
    (task,) = PostgresWarehouse().apply_tasks(plan_of(root))
    return task.sql
