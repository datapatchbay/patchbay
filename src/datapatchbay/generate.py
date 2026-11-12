"""Generating the files of every data product through the plugins named in the settings."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from datapatchbay.capabilities import committed_outputs
from datapatchbay.errors import GenerationError
from datapatchbay.filewrite import write_file
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
        committed: The committed files that executors wrote into the repo, relative to the repo root.
        removed: The generated committed files deleted because nothing produces them any more, relative to the repo
            root, sorted.
    """

    report: Report
    output_dir: Path
    files: tuple[PurePosixPath, ...]
    committed: tuple[PurePosixPath, ...] = ()
    removed: tuple[PurePosixPath, ...] = ()


def generate_repo(root: Path, *, output_dir: Path | None = None) -> GenerateResult:
    """Validate the repo, generate every data product's files in memory and write them.

    The repo is planned once by `plan_repo`; the committed file diff, the plan checks of the executors and the stale
    output checks of `validate_repo` do not run. Nothing is written when the repo is invalid or when any data product
    fails to generate (the report holds those problems), so generation is all-or-nothing. The writing itself is not:
    each file is written to a temporary file and moved into place, so a reader never sees half a file, but a failure
    part-way (a full disk, a permission) leaves the files already moved in place.
    The order limits the damage: output folder first, then the committed files of the executors, which each order
    their own writes. Output files left from an earlier run are not removed.

    The executors that produce committed files (the capability `WritesCommittedFiles`) say what they write and delete;
    their documentation says how.

    Args:
        root: The repo root.

    Keyword Args:
        output_dir: The folder to write to. Defaults to the `output_dir` setting, relative to the repo root.

    Raises:
        GenerationError: If a file cannot be written or deleted, or an executor cannot write its committed files; the
            message says which.
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

    # Committed files are source files, not build output, so an executor puts them next to the data products.
    committed_output = committed_outputs(planned)
    committed_output.check_writable()  # before any write, so a repo an executor cannot write to stays as it was

    for path, content in files.items():
        write_file(target / path, content)
    committed = committed_output.write()
    return GenerateResult(planned.report, target, tuple(sorted(files)), committed, committed_output.orphans)
