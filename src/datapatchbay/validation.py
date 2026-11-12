"""Validating a whole repo: each file on its own, then the links between files."""

from pathlib import Path

from datapatchbay.crosschecks import check_repo
from datapatchbay.loading import load_repo
from datapatchbay.problems import Report


def validate_repo(root: Path) -> Report:
    """Validate `datapatchbay.yaml`, every data product, every port and every table.

    Every file is checked even when an earlier one has problems, so one run reports everything. Cross-file checks
    run on whatever loaded and skip what depends on a file that did not.
    """
    repo, problems = load_repo(root)
    problems.extend(check_repo(repo))
    return Report(dataproducts_checked=repo.dataproduct_dirs, problems=problems)
