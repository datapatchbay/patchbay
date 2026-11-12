"""Land the jaffle shop's orders in the private schema of the data product."""

from datetime import datetime

SCHEMA = "sa_jaffle_orders_private"

# A stand-in for the shop's order system. A real build would call the source's API or read its export.
ORDERS = [
    ("JO-1", "C-100", "completed", datetime(2025, 3, 3, 8, 0), datetime(2025, 3, 5, 8, 0)),
    ("JO-2", "C-101", "completed", datetime(2025, 3, 3, 9, 30), datetime(2025, 3, 4, 9, 30)),
    ("JO-3", "C-102", "placed", datetime(2025, 3, 4, 10, 15), None),
]


def build() -> None:
    """Replace `ingested_orders` with the orders of the shop's order system.

    The warehouse is reached through the Airflow connection `warehouse`, because this runs on the worker runtime.
    """
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    hook = PostgresHook(postgres_conn_id="warehouse")
    hook.run(
        [
            f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"',
            f'DROP TABLE IF EXISTS "{SCHEMA}"."ingested_orders"',
            f'CREATE TABLE "{SCHEMA}"."ingested_orders" (order_id text, customer_id text, status text,'
            " ordered_at timestamp, completed_at timestamp)",
        ]
    )
    hook.insert_rows(
        f'"{SCHEMA}"."ingested_orders"',
        ORDERS,
        target_fields=["order_id", "customer_id", "status", "ordered_at", "completed_at"],
    )
