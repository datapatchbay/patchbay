import os
from collections.abc import Iterator

import psycopg
import pytest


@pytest.fixture
def pg() -> Iterator[psycopg.Connection]:
    """A connection to the Postgres that the standard `PG*` environment variables name; skips when none is set.

    CI starts a Postgres service and sets `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` and `PGDATABASE`. Locally, run
    any Postgres and export the same variables to include the tests that use it.
    """
    if not os.environ.get("PGHOST"):
        pytest.skip("PGHOST is not set; no Postgres to run against")
    with psycopg.connect(autocommit=True) as connection:
        yield connection
