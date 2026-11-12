"""Build code of the integration test: it writes a row that breaks the `not_null` rule of the table."""

import os

import duckdb

SCHEMA = "sa_broken_private"


def build() -> None:
    with duckdb.connect(os.environ["DPB_TEST_DUCKDB"]) as db:
        db.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        db.execute(f"CREATE OR REPLACE TABLE {SCHEMA}.orders AS SELECT * FROM (VALUES ('O-1'), (NULL)) t(order_id)")
