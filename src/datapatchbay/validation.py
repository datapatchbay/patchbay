"""Validating a whole repo: stage 1 is the gate that plans, stage 2 compares the plans with what is on disk."""

from pathlib import Path

from datapatchbay.conventions import check_conventions
from datapatchbay.crosschecks import check_repo
from datapatchbay.dbt import check_dbt
from datapatchbay.dbt_manifest import check_dbt_reads
from datapatchbay.dbt_output import build_dbt_output
from datapatchbay.freshness import check_freshness
from datapatchbay.loading import load_repo
from datapatchbay.planning import PlannedRepo, plan_dataproducts
from datapatchbay.pluginchecks import check_plugins
from datapatchbay.problems import Report
from datapatchbay.rendering import render_dataproducts
from datapatchbay.settings import EffectiveSettings, resolve_settings
from datapatchbay.staleoutput import check_stale_output


def plan_repo(root: Path) -> PlannedRepo | Report:
    """Stage 1: load and check `datapatchbay.yaml`, every data product, every port and every table, then plan.

    Every file is checked even when an earlier one has problems, so one run reports everything. Cross-file checks
    run on whatever loaded and skip what depends on a file that did not. The convention, plugin and dbt checks need
    valid settings, so they are skipped when `datapatchbay.yaml` is invalid, which the report already says.

    Returns:
        The report when anything is wrong, otherwise the planned repo, whose plans were computed once.
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
    if settings is None or problems:
        return Report(dataproducts_checked=repo.dataproduct_dirs, problems=problems)
    return PlannedRepo(repo, settings, plan_dataproducts(repo, settings))


def validate_repo(root: Path) -> Report:
    """Validate a repo and return the report. See `plan_repo`.

    Once stage 1 passes, stage 2 runs every check on the shared plans and reports all problems in one run: the
    committed dbt files are compared with what `dpb generate` would write, what the dbt models read is compared with
    the input ports (the dbt manifest must exist), the data products are rendered in memory to find what would make
    `dpb generate` fail, such as a table named `dbt` next to tables built by dbt, or source input ports with different
    schedules, and stale output files are looked for. Nothing is written.
    """
    planned = plan_repo(root)
    if isinstance(planned, Report):
        return planned
    target = root / planned.settings.values.output_dir
    problems = [
        *build_dbt_output(planned).problems(),
        *check_dbt_reads(planned),
        *render_dataproducts(planned, target).problems,
        *check_stale_output(planned),
    ]
    return Report(dataproducts_checked=planned.report.dataproducts_checked, problems=problems)
