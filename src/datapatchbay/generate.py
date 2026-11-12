"""Generating the files of every data product through the plugins named in the settings."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from datapatchbay.errors import GenerationError
from datapatchbay.filewrite import write_file
from datapatchbay.integrations.dbt.output import build_dbt_output
from datapatchbay.problems import Report
from datapatchbay.rendering import render_dataproducts
from datapatchbay.validation import plan_repo

__all__ = ["GenerateResult", "GenerationError", "generate_repo"]


@dataclass(frozen=True, slots=True)
class GenerateResult:
    """The result of `generate_repo`.

    Attributes:
        report: The validation report. Nothing was written unless it is ok. It holds the problems of
            validation and of rendering.
        output_dir: The folder the files went to.
        files: The files written to the output folder, relative to it, sorted.
        committed: The committed files written into the repo (dbt properties, then `dbt_project.yml` when it
            changed), relative to the repo root.
        removed: The generated dbt properties files deleted because no table file produces them any more, relative
            to the repo root, sorted.
    """

    report: Report
    output_dir: Path
    files: tuple[PurePosixPath, ...]
    committed: tuple[PurePosixPath, ...] = ()
    removed: tuple[PurePosixPath, ...] = ()


def generate_repo(root: Path, *, output_dir: Path | None = None) -> GenerateResult:
    """Validate the repo, generate every data product's files in memory and write them.

    The repo is planned once by `plan_repo`; the dbt file diff, the manifest reads and the stale output checks of
    `validate_repo` do not run. Nothing is written when the repo is invalid or when any data product fails to
    generate (the report holds those problems), so generation is all-or-nothing. The writing itself is not: each
    file is written to a temporary file and moved into place, so a reader never sees half a file, but a failure
    part-way (a full disk, a permission) leaves the files already moved in place.
    The order limits the damage: output folder first, then the dbt properties, then the deletions, and
    `dbt_project.yml` last. Output files left from an earlier run are not removed.

    When tables are built by dbt, the `model-paths` and `test-paths` of `dbt_project.yml` at the repo root (not in
    `output_dir`, because the file is committed) are also brought in step, only if that is needed,
    and only those keys change. Once any table is built by dbt, `dpb generate` owns both keys: a hand-set entry is
    replaced. When no table is built by dbt any more, only the entries that point at the `models/` or `tests/` folder
    of a data product are removed.
    The dbt properties, sources and singular test files, also committed, are written next to the models. A file that
    carries the generated header but is no longer produced (its table is gone or no longer built by dbt) is deleted.

    Args:
        root: The repo root.

    Keyword Args:
        output_dir: The folder to write to. Defaults to the `output_dir` setting, relative to the repo root.

    Raises:
        GenerationError: If a file cannot be written or deleted, or tables
            are built by dbt and the repo root has no usable `dbt_project.yml`; the message says which.
        PluginNotFoundError: If a plugin is missing. The gate reports that first, so this means a plugin vanished.
    """
    planned = plan_repo(root)
    if isinstance(planned, Report):
        return GenerateResult(planned, (output_dir or root).resolve(), ())
    target = (output_dir or root / planned.settings.values.output_dir).resolve()

    rendered = render_dataproducts(planned, target)
    if rendered.problems:
        return GenerateResult(Report(planned.report.dataproducts_checked, rendered.problems), target, ())
    files = rendered.files

    # The dbt properties, sources and tests are committed source files, not build output, so they go next to the models.
    dbt_output = build_dbt_output(planned)
    if dbt_output.project_error is not None:  # before any write, so a repo without a usable dbt project stays as it was
        raise GenerationError(dbt_output.project_error)

    for path, content in files.items():
        write_file(target / path, content)
    committed = dbt_output.write()
    return GenerateResult(planned.report, target, tuple(sorted(files)), committed, dbt_output.orphans)
