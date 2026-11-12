"""Build code of the integration test: it connects by itself, as build code does (ADR-0001)."""

import os

import duckdb

SCHEMA = "sa_shop_private"


def build() -> None:
    with duckdb.connect(os.environ["DPB_TEST_DUCKDB"]) as db:
        db.execute(
            f"""CREATE OR REPLACE TABLE {SCHEMA}.orders AS
            SELECT order_id, 'C-' || right(order_id, 1) AS customer_id, 'placed' AS status
            FROM {SCHEMA}.ingested_orders"""
        )
