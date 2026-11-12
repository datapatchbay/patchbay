"""Integration tests: they need a Postgres server, started by `scripts/integration-tests` (ADR-0020)."""

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Every test in this folder is an integration test, so it carries the marker that `uv run pytest` deselects."""
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)


@pytest.fixture
def postgres_admin() -> Iterator[psycopg.Connection]:
    """A connection to the server that `DPB_TEST_POSTGRES_URL` names, whose user may create databases and roles.

    `scripts/integration-tests` starts the server in Docker and sets the variable. Without it the test fails, because
    an integration test that is selected must run.
    """
    url = os.environ.get("DPB_TEST_POSTGRES_URL")
    if not url:
        pytest.fail("DPB_TEST_POSTGRES_URL is not set; run the integration tests with scripts/integration-tests")
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
