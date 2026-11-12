"""Generating the files of every data product through the plugins named in the settings."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from datapatchbay.dbt_project import DbtProjectError, synced_dbt_project
from datapatchbay.dbt_properties import generate_dbt_properties
from datapatchbay.dbt_tests import generate_dbt_tests
from datapatchbay.errors import DatapatchbayError
from datapatchbay.planning import plan_dataproducts
from datapatchbay.plugins import (
    DataProductPlan,
    Executor,
    GeneratedFile,
    GenerationContext,
    Orchestrator,
    Runtime,
    UnsupportedCombinationError,
    Warehouse,
)
from datapatchbay.problems import Report
from datapatchbay.registry import load_plugin
from datapatchbay.settings import EffectiveSettings, load_settings
from datapatchbay.validation import load_and_validate


class GenerationError(DatapatchbayError):
    """Raised when a plugin cannot generate a data product."""


@dataclass(frozen=True, slots=True)
class GenerateResult:
    """The result of `generate_repo`.

    Attributes:
        report: The validation report. Nothing was written unless it is ok.
        output_dir: The folder the files went to.
        files: The files written, relative to the output folder, sorted.
    """

    report: Report
    output_dir: Path
    files: tuple[PurePosixPath, ...]


def generate_repo(root: Path, *, output_dir: Path | None = None) -> GenerateResult:
    """Validate the repo, generate every data product's files in memory and write them.

    Nothing is written when the repo is invalid or when any data product fails to generate, so the output folder is
    never left with half a run. Files left from an earlier run are not removed.

    When tables are built by dbt, the `model-paths` and `test-paths` of `dbt_project.yml` at the repo root (not in
    `output_dir`, because the file is committed) are also brought in step, after all other files are written, and only
    if that is needed. The dbt properties files and singular tests, also committed, are written just before it, next
    to the models.

    Args:
        root: The repo root.

    Keyword Args:
        output_dir: The folder to write to. Defaults to the `output_dir` setting, relative to the repo root.

    Raises:
        GenerationError: If a plugin cannot generate a data product, or tables are built by dbt and the repo root has
            no usable `dbt_project.yml`; the message says which.
        PluginNotFoundError: If a plugin is missing. Validation reports that first, so this means a plugin vanished.
    """
    repo, report = load_and_validate(root)
    if not report.ok:
        return GenerateResult(report, (output_dir or root).resolve(), ())
    settings = load_settings(root)
    target = (output_dir or root / settings.values.output_dir).resolve()

    plans = plan_dataproducts(repo, settings)
    files: dict[PurePosixPath, str] = {}
    for plan in plans:
        for generated in _generate(plan, root, target, settings):
            if generated.path in files:
                raise GenerationError(f"data product '{plan.folder}': file {generated.path} is generated twice")
            files[generated.path] = generated.content

    # The dbt properties are committed source files of the repo, not build output, so they go next to the models.
    properties = [*generate_dbt_properties(plans, settings), *generate_dbt_tests(plans, settings)]

    try:
        dbt_project = synced_dbt_project(repo, settings)
    except DbtProjectError as exc:
        raise GenerationError(str(exc)) from exc

    for path, content in files.items():
        destination = target / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content.encode("utf-8"))
    for generated in properties:
        destination = root / generated.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(generated.content.encode("utf-8"))
    if dbt_project is not None:  # last, so a failed write above leaves the committed file as it was
        dbt_project[0].write_bytes(dbt_project[1].encode("utf-8"))
    return GenerateResult(report, target, tuple(sorted(files)))


def _generate(plan: DataProductPlan, root: Path, target: Path, settings: EffectiveSettings) -> list[GeneratedFile]:
    orchestrator: Orchestrator = load_plugin("orchestrator", plan.orchestrator)
    warehouse: Warehouse = load_plugin("warehouse", settings.values.warehouse)
    executors: dict[str, Executor] = {
        name: load_plugin("executor", name) for name in sorted({t.executor for t in plan.tables})
    }
    runtimes: dict[str, Runtime] = {
        name: load_plugin("runtime", name) for name in sorted({t.runtime for t in plan.tables})
    }
    context = GenerationContext(
        root=root, output_dir=target, executors=executors, runtimes=runtimes, warehouse=warehouse
    )
    try:
        return list(orchestrator.generate(plan, context))
    except UnsupportedCombinationError as exc:
        raise GenerationError(f"data product '{plan.folder}': {exc}") from exc
