"""Validating a whole repo: each file on its own, then the links between files."""

from pathlib import Path
from typing import NamedTuple

from datapatchbay.conventions import check_conventions
from datapatchbay.crosschecks import check_repo
from datapatchbay.dbt import check_dbt
from datapatchbay.dbt_manifest import check_dbt_reads
from datapatchbay.dbt_sync import check_dbt_files
from datapatchbay.freshness import check_freshness
from datapatchbay.loading import load_repo
from datapatchbay.pluginchecks import check_plugins
from datapatchbay.problems import Report
from datapatchbay.rendering import check_generation
from datapatchbay.repomodel import Repo
from datapatchbay.settings import EffectiveSettings, resolve_settings
from datapatchbay.staleoutput import check_stale_output


class Validation(NamedTuple):
    """What `load_and_validate` found.

    Attributes:
        repo: What loaded. Use it only when the report is ok.
        settings: The effective settings, built once from the root file. `None` when `datapatchbay.yaml` is invalid.
        report: The problems found.
    """

    repo: Repo
    settings: EffectiveSettings | None
    report: Report


def load_and_validate(root: Path) -> Validation:
    """Load and validate `datapatchbay.yaml`, every data product, every port and every table.

    Every file is checked even when an earlier one has problems, so one run reports everything. Cross-file checks
    run on whatever loaded and skip what depends on a file that did not. The convention and plugin checks need
    valid settings, so they are skipped when `datapatchbay.yaml` is invalid, which the report already says.

    Returns:
        What loaded, the settings and the report. Use the repo only when the report is ok.
    """
    repo, problems = load_repo(root)
    problems.extend(check_repo(repo))
    problems.extend(check_freshness(repo))
    settings: EffectiveSettings | None = None
    if repo.root_file is not None:  # otherwise `load_repo` reported it, and no convention or plugin can be checked
        settings = resolve_settings(repo.root_file)
        problems.extend(check_conventions(repo, settings, repo.root_file.data))
        problems.extend(check_plugins(repo, settings, repo.root_file.data))
        problems.extend(check_dbt(repo, settings))
    return Validation(repo, settings, Report(dataproducts_checked=repo.dataproduct_dirs, problems=problems))


def validate_repo(root: Path) -> Report:
    """Validate a repo and return the report. See `load_and_validate`.

    On top of that, once everything else is valid, the committed dbt files are compared with what `dpb generate`
    would write, what the dbt models read is compared with the input ports (the dbt manifest must exist), and the data
    products are generated in memory to find what would make `dpb generate` fail, such as a table named `dbt` next to
    tables built by dbt, or source input ports with different schedules. `dpb generate` uses `load_and_validate` and
    skips all of these, because it is what refreshes the files and reports the failures itself. Nothing is written.
    """
    repo, settings, report = load_and_validate(root)
    if settings is None or not report.ok:
        return report
    problems = [
        *check_dbt_files(repo, settings),
        *check_dbt_reads(repo, settings),
        *check_generation(repo, settings, root),
        *check_stale_output(repo, settings),
    ]
    return Report(dataproducts_checked=report.dataproducts_checked, problems=problems)
