"""Validating a whole repo: each file on its own, then the links between files."""

from pathlib import Path

from datapatchbay.conventions import check_conventions
from datapatchbay.crosschecks import check_repo
from datapatchbay.dbt import check_dbt
from datapatchbay.freshness import check_freshness
from datapatchbay.loading import load_repo
from datapatchbay.pluginchecks import check_plugins
from datapatchbay.problems import Report
from datapatchbay.repo import ROOT_FILE
from datapatchbay.repomodel import Repo
from datapatchbay.settings import InvalidSettingsError, load_settings
from datapatchbay.yamlio import load_mapping


def load_and_validate(root: Path) -> tuple[Repo, Report]:
    """Load and validate `datapatchbay.yaml`, every data product, every port and every table.

    Every file is checked even when an earlier one has problems, so one run reports everything. Cross-file checks
    run on whatever loaded and skip what depends on a file that did not. The convention and plugin checks need
    valid settings, so they are skipped when `datapatchbay.yaml` is invalid, which the report already says.

    Returns:
        What loaded, and the report. Use the repo only when the report is ok.
    """
    repo, problems = load_repo(root)
    problems.extend(check_repo(repo))
    problems.extend(check_freshness(repo))
    try:
        settings = load_settings(root)
    except InvalidSettingsError:
        pass  # `load_repo` reported `datapatchbay.yaml`; without settings no convention or plugin can be checked.
    else:
        problems.extend(check_conventions(repo, settings, load_mapping(root / ROOT_FILE)))
        problems.extend(check_plugins(repo, settings))
        problems.extend(check_dbt(repo, settings))
    return repo, Report(dataproducts_checked=repo.dataproduct_dirs, problems=problems)


def validate_repo(root: Path) -> Report:
    """Validate a repo and return the report. See `load_and_validate`."""
    return load_and_validate(root)[1]
