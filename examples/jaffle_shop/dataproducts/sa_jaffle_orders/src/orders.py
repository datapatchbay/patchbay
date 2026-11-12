"""Build the orders of the output port from the ingested orders."""

SCHEMA = "sa_jaffle_orders_private"


def build() -> None:
    """Replace `orders` with the ingested orders, one row per order."""
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    PostgresHook(postgres_conn_id="warehouse").run(
        [
            f'DROP TABLE IF EXISTS "{SCHEMA}"."orders"',
            f'CREATE TABLE "{SCHEMA}"."orders" AS'
            " SELECT DISTINCT ON (order_id) order_id, customer_id, status, ordered_at, completed_at"
            f' FROM "{SCHEMA}"."ingested_orders" ORDER BY order_id, ordered_at DESC',
        ]
    )
