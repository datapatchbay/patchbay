"""Validating a whole repo: stage 1 is the gate that plans, stage 2 compares the plans with what is on disk."""

from pathlib import Path

from datapatchbay.checks.conventions import check_conventions
from datapatchbay.checks.crosschecks import check_repo
from datapatchbay.checks.freshness import check_freshness
from datapatchbay.checks.pluginchecks import check_plugins
from datapatchbay.files.loading import load_repo
from datapatchbay.pipeline.capabilities import check_executor_files, check_executor_plans, committed_outputs
from datapatchbay.pipeline.planning import plan_dataproducts
from datapatchbay.pipeline.rendering import render_dataproducts
from datapatchbay.pipeline.staleoutput import check_stale_output
from datapatchbay.plugins import PlannedRepo
from datapatchbay.problems import Report
from datapatchbay.settings.cascade import ResolvedCascade, resolve_cascade
from datapatchbay.settings.effective import EffectiveSettings, resolve_settings


def plan_repo(root: Path) -> PlannedRepo | Report:
    """Stage 1: load and check `datapatchbay.yaml`, every data product, every port and every table, then plan.

    Every file is checked even when an earlier one has problems, so one run reports everything. Cross-file checks
    run on whatever loaded and skip what depends on a file that did not. The convention, plugin and executor checks need
    valid settings, so they are skipped when `datapatchbay.yaml` is invalid, which the report already says.

    Returns:
        The report when anything is wrong, otherwise the planned repo, whose plans were computed once.
    """
    repo, problems = load_repo(root)
    problems.extend(check_repo(repo))
    problems.extend(check_freshness(repo))
    settings: EffectiveSettings | None = None
    cascade: ResolvedCascade | None = None
    if repo.root_file is not None:  # otherwise `load_repo` reported it, and no convention or plugin can be checked
        settings = resolve_settings(repo.root_file)
        cascade = resolve_cascade(repo, settings)
        problems.extend(check_conventions(repo, settings, repo.root_file.data))
        problems.extend(check_plugins(repo, settings, cascade, repo.root_file.data))
        problems.extend(check_executor_files(repo, settings, cascade))
    if settings is None or cascade is None or problems:
        return Report(dataproducts_checked=repo.dataproduct_dirs, problems=problems)
    return PlannedRepo(repo, settings, plan_dataproducts(repo, settings, cascade))


def validate_repo(root: Path) -> Report:
    """Validate a repo and return the report. See `plan_repo`.

    Once stage 1 passes, stage 2 runs every check on the shared plans and reports all problems in one run: the
    committed files of the executors are compared with what `dpb generate` would write, the executors check the plans
    against what is on disk (what their models read against the input ports), the data products are rendered in
    memory to find what would make `dpb generate` fail, such as source input ports with different schedules, and
    stale output files are looked for. Nothing is written.
    """
    planned = plan_repo(root)
    if isinstance(planned, Report):
        return planned
    target = root / planned.settings.values.output_dir
    problems = [
        *committed_outputs(planned).problems(),
        *check_executor_plans(planned),
        *render_dataproducts(planned, target).problems,
        *check_stale_output(planned),
    ]
    return Report(dataproducts_checked=planned.report.dataproducts_checked, problems=problems)
