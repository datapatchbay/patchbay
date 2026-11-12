"""Generating the files of every data product through the plugins named in the settings."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

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

    Args:
        root: The repo root.

    Keyword Args:
        output_dir: The folder to write to. Defaults to the `output_dir` setting, relative to the repo root.

    Raises:
        GenerationError: If a plugin cannot generate a data product; the message names it.
        PluginNotFoundError: If a plugin is missing. Validation reports that first, so this means a plugin vanished.
    """
    repo, report = load_and_validate(root)
    if not report.ok:
        return GenerateResult(report, (output_dir or root).resolve(), ())
    settings = load_settings(root)
    target = (output_dir or root / settings.values.output_dir).resolve()

    files: dict[PurePosixPath, str] = {}
    for plan in plan_dataproducts(repo, settings):
        for generated in _generate(plan, root, target, settings):
            if generated.path in files:
                raise GenerationError(f"data product '{plan.folder}': file {generated.path} is generated twice")
            files[generated.path] = generated.content

    for path, content in files.items():
        destination = target / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content.encode("utf-8"))
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
