"""Build code of the integration test: it connects by itself, as build code does (ADR-0001)."""

import os

import duckdb

SCHEMA = "sa_shop_private"


def build() -> None:
    with duckdb.connect(os.environ["DPB_TEST_DUCKDB"]) as db:
        db.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        db.execute(
            f"CREATE OR REPLACE TABLE {SCHEMA}.ingested_orders AS SELECT 'O-' || i AS order_id FROM range(1, 4) t(i)"
        )
