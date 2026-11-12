import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo


@pytest.fixture
def postgres_admin() -> Iterator[psycopg.Connection]:
    """A connection to the server that `DPB_TEST_POSTGRES_URL` names, whose user may create databases and roles.

    CI starts a Postgres service and sets the variable in its `postgres` job. Locally, export the URL of any Postgres
    to include the tests marked `postgres`; without it they are skipped. A local server is the deviation from the
    rule that tests stay off the network: the SQL that dpb generates can only be checked by running it.
    """
    url = os.environ.get("DPB_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("DPB_TEST_POSTGRES_URL is not set")
    with psycopg.connect(url, autocommit=True) as admin:
        yield admin


@pytest.fixture
def pg_db(postgres_admin: psycopg.Connection) -> Iterator[psycopg.Connection]:
    """An autocommit connection to a fresh, empty database that is dropped after the test."""
    database = f"dpb_test_{uuid.uuid4().hex[:12]}"
    postgres_admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    url = os.environ["DPB_TEST_POSTGRES_URL"]
    with psycopg.connect(make_conninfo(url, dbname=database), autocommit=True) as connection:
        yield connection
    postgres_admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
