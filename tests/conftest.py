"""Fixtures shared by the unit tests (`tests/datapatchbay/`) and the integration tests (`tests/integration/`)."""

import shutil
from pathlib import Path

import pytest

JAFFLE_REPO = Path(__file__).parent / "airflow" / "repo"


DBT_FIXTURE = frozenset({"dbt_project.yml", "models", "weekly_summary.yaml"})
"""The files of the fixture repo that exist for the table built by dbt, which most tests do without."""


@pytest.fixture
def jaffle_repo(tmp_path: Path) -> Path:
    """A copy of the valid fixture repo that the integration tests load in Airflow, without its table built by dbt.

    A source-fed data product and its reader, and a data product that mixes runtimes.
    """
    root = tmp_path / "repo"
    shutil.copytree(JAFFLE_REPO, root, ignore=lambda _folder, names: DBT_FIXTURE.intersection(names))
    return root


@pytest.fixture
def jaffle_dbt_repo(tmp_path: Path) -> Path:
    """A copy of the whole fixture repo, where `agg_weekly_orders` also has a table that dbt builds."""
    root = tmp_path / "repo"
    shutil.copytree(JAFFLE_REPO, root)
    return root
