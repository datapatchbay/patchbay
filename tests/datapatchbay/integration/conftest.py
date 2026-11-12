"""Integration tests: they need a Postgres server, started by `scripts/integration-tests` (ADR-0020)."""

import os
import subprocess
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

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


# The Dockerfile and the scripts that run in the container.
AIRFLOW_DIR = Path(__file__).parents[3] / "tests" / "airflow"
SCRIPTS = "/scripts"


@pytest.fixture(scope="session")
def airflow_image() -> str:
    """The image with Airflow 3, its providers and dbt, built from `tests/airflow/Dockerfile` (layers are cached)."""
    tag = "dpb-integration-tests-airflow"
    build = subprocess.run(
        ["docker", "build", "--quiet", "--tag", tag, str(AIRFLOW_DIR)], capture_output=True, text=True, check=False
    )
    assert build.returncode == 0, f"docker build failed:\n{build.stdout}\n{build.stderr}"
    return tag


@pytest.fixture
def run_in_airflow(airflow_image: str) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Run `python /scripts/<script> <arguments>` in a throwaway Airflow container; return the finished process.

    Each folder in `mounts` is mounted at its own path, read-only, so the relative paths in a generated DAG file
    resolve in the container as they do on the host. With `network`, the container joins the Docker network of the
    Postgres container.
    """

    def run(
        script: str, arguments: list[str], mounts: list[Path], *, network: bool = False
    ) -> subprocess.CompletedProcess[str]:
        command = ["docker", "run", "--rm", "--label", "dpb-integration-tests"]
        if network:
            command += ["--network", os.environ["DPB_TEST_DOCKER_NETWORK"]]
        for mount in mounts:
            command += ["--volume", f"{mount}:{mount}:ro"]
        command += [
            "--volume",
            f"{AIRFLOW_DIR}:{SCRIPTS}:ro",
            airflow_image,
            "python",
            f"{SCRIPTS}/{script}",
            *arguments,
        ]
        return subprocess.run(command, capture_output=True, text=True, check=False)

    return run
