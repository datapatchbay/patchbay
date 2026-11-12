"""Planning a repo for tests that start from files on disk."""

from pathlib import Path

from datapatchbay.cascade import resolve_cascade
from datapatchbay.planning import plan_dataproducts
from datapatchbay.plugins import DataProductPlan
from datapatchbay.repomodel import Repo
from datapatchbay.settings import load_settings


def plan_all(repo: Repo, root: Path) -> list[DataProductPlan]:
    """Resolve the settings and the cascade of the repo at `root`, then plan every data product."""
    settings = load_settings(root)
    return plan_dataproducts(repo, settings, resolve_cascade(repo, settings))
