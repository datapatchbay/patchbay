"""Validating a whole repo: each file on its own, then the links between files."""

from pathlib import Path

from datapatchbay.conventions import check_conventions
from datapatchbay.crosschecks import check_repo
from datapatchbay.freshness import check_freshness
from datapatchbay.loading import load_repo
from datapatchbay.problems import Report
from datapatchbay.repo import ROOT_FILE
from datapatchbay.settings import InvalidSettingsError, load_settings
from datapatchbay.yamlio import load_mapping


def validate_repo(root: Path) -> Report:
    """Validate `datapatchbay.yaml`, every data product, every port and every table.

    Every file is checked even when an earlier one has problems, so one run reports everything. Cross-file checks
    run on whatever loaded and skip what depends on a file that did not.
    """
    repo, problems = load_repo(root)
    problems.extend(check_repo(repo))
    try:
        settings = load_settings(root)
    except InvalidSettingsError:
        pass  # `load_repo` reported `datapatchbay.yaml`; without settings no convention can be checked.
    else:
        problems.extend(check_conventions(repo, settings, load_mapping(root / ROOT_FILE)))
    problems.extend(check_freshness(repo))
    return Report(dataproducts_checked=repo.dataproduct_dirs, problems=problems)
