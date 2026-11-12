"""Land the lab system's orders in the private schema of the data product."""

from datetime import datetime

SCHEMA = "sa_ilab_orders_private"

# A stand-in for the lab system. A real build would call the source's API or read its export.
ORDERS = [
    ("LO-1", "P-100", "closed", datetime(2025, 3, 3, 8, 0), datetime(2025, 3, 5, 8, 0)),
    ("LO-2", "P-101", "closed", datetime(2025, 3, 3, 9, 30), datetime(2025, 3, 4, 9, 30)),
    ("LO-3", "P-102", "open", datetime(2025, 3, 4, 10, 15), None),
]


def build() -> None:
    """Replace `ingested_orders` with the orders of the lab system.

    The warehouse is reached through the Airflow connection `warehouse`, because this runs on the worker runtime.
    """
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    hook = PostgresHook(postgres_conn_id="warehouse")
    hook.run(
        [
            f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"',
            f'DROP TABLE IF EXISTS "{SCHEMA}"."ingested_orders"',
            f'CREATE TABLE "{SCHEMA}"."ingested_orders" (order_id text, patient_id text, status text,'
            " ordered_at timestamp, completed_at timestamp)",
        ]
    )
    hook.insert_rows(
        f'"{SCHEMA}"."ingested_orders"',
        ORDERS,
        target_fields=["order_id", "patient_id", "status", "ordered_at", "completed_at"],
    )
