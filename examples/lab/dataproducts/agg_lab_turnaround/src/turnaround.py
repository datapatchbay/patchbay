"""Build the turnaround of completed orders from the output port of `sa_ilab_orders`."""

SCHEMA = "agg_lab_turnaround_private"


def build() -> None:
    """Replace `turnaround`. It reads the output port `sa_ilab_orders`, never that data product's private schema."""
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    PostgresHook(postgres_conn_id="warehouse").run(
        [
            f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"',
            f'DROP TABLE IF EXISTS "{SCHEMA}"."turnaround"',
            f'CREATE TABLE "{SCHEMA}"."turnaround" AS'
            " SELECT order_id, extract(epoch FROM completed_at - ordered_at) / 3600 AS turnaround_hours, ordered_at"
            ' FROM "sa_ilab_orders"."orders" WHERE completed_at IS NOT NULL',
        ]
    )
