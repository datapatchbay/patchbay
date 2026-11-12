"""A generated `local` script run against a real Postgres, through `psycopg.connect(url, autocommit=True)`.

Integration tests: the multi-statement apply SQL with its grants, and the audits, run on a real server (ADR-0020).
"""

import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from local_support import SA, generate, run_script, write_repo
from psycopg import sql

READER = "grp-local-reporting"
ROLES = (READER, "dp_agg_order_totals")

SETTINGS = "schema_version: 1\norchestrator: local\nwarehouse: postgres\nruntime: worker\n"

BUILD_RAW = """\
import os
from urllib.parse import urlsplit, urlunsplit

import psycopg


def build():
    with psycopg.connect(os.environ["DPB_CONNECTION_WAREHOUSE"], autocommit=True) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS sa_shop_orders_private")
        connection.execute("DROP TABLE IF EXISTS sa_shop_orders_private.raw_orders")
        connection.execute(
            "CREATE TABLE sa_shop_orders_private.raw_orders AS SELECT * FROM generate_series(1, 3) AS order_id"
        )
"""

BUILD_ORDERS = """\
import os
from urllib.parse import urlsplit, urlunsplit

import psycopg

EXTRA = {extra!r}


def build():
    with psycopg.connect(os.environ["DPB_CONNECTION_WAREHOUSE"], autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS sa_shop_orders_private.orders")
        connection.execute(
            "CREATE TABLE sa_shop_orders_private.orders AS "
            "SELECT order_id::integer AS order_id FROM sa_shop_orders_private.raw_orders" + EXTRA
        )
"""

PORT = f"schema_version: 1\nkind: schema\naccess:\n  readers:\n    - {READER}\n    - product: agg_order_totals\n"


def repo(root: Path, extra: str = "") -> Path:
    """The shop repo on Postgres, where `extra` is added to the query that builds `orders`."""
    return write_repo(
        root,
        **{
            "datapatchbay.yaml": SETTINGS,
            f"{SA}/src/raw.py": BUILD_RAW,
            f"{SA}/src/orders.py": BUILD_ORDERS.format(extra=extra),
            f"{SA}/outputs/sa_shop_orders/port.yaml": PORT,
        },
    )


@pytest.fixture
def reader(postgres_admin: psycopg.Connection) -> Iterator[None]:
    """The reader role, which `dpb` expects to exist (ADR-0017); roles belong to the server, so drop it afterwards."""
    for role in ROLES:
        postgres_admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
    yield
    for role in ROLES:
        postgres_admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


def url_of(connection: psycopg.Connection) -> str:
    """The URL of the server with the database of the test, which is the form the script reads."""
    server = urlsplit(os.environ["DPB_TEST_POSTGRES_URL"])
    return urlunsplit(server._replace(path=f"/{connection.info.dbname}"))


def test_the_script_builds_audits_and_applies_the_views_so_the_reader_can_select(
    tmp_path: Path, reader: None, pg_db: psycopg.Connection
):
    script = generate(repo(tmp_path)) / "sa_shop_orders.py"

    done = run_script(script, url=url_of(pg_db))

    assert done.returncode == 0, done.stderr
    view = "SELECT order_id FROM sa_shop_orders.orders ORDER BY 1"
    assert pg_db.execute(view).fetchall() == [(1,), (2,), (3,)]
    pg_db.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(READER)))
    try:
        assert pg_db.execute(view).fetchall() == [(1,), (2,), (3,)]
    finally:
        pg_db.execute("RESET ROLE")


def test_a_broken_error_rule_exits_non_zero_and_the_views_are_not_applied(
    tmp_path: Path, reader: None, pg_db: psycopg.Connection
):
    script = generate(repo(tmp_path, extra=" UNION ALL SELECT NULL::integer")) / "sa_shop_orders.py"

    done = run_script(script, url=url_of(pg_db))

    assert done.returncode != 0
    assert "quality rule 'not_null' is broken on table 'orders', column 'order_id': 1 violation(s)" in done.stderr
    assert pg_db.execute("SELECT count(*) FROM pg_namespace WHERE nspname = 'sa_shop_orders'").fetchone() == (0,)
