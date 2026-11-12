"""Generating the files of every data product through the plugins named in the settings."""

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from datapatchbay.dbt_project import DbtProjectError, synced_dbt_project
from datapatchbay.dbt_properties import generate_dbt_properties
from datapatchbay.dbt_sync import orphaned_dbt_properties
from datapatchbay.planning import plan_dataproducts
from datapatchbay.problems import Report
from datapatchbay.rendering import GenerationError, render_dataproducts
from datapatchbay.settings import load_settings
from datapatchbay.validation import load_and_validate

__all__ = ["GenerateResult", "GenerationError", "generate_repo"]


@dataclass(frozen=True, slots=True)
class GenerateResult:
    """The result of `generate_repo`.

    Attributes:
        report: The validation report. Nothing was written unless it is ok.
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

    Nothing is written when the repo is invalid or when any data product fails to generate, so generation is
    all-or-nothing. The writing itself is not: each file is written to a temporary file and moved into place, so a
    reader never sees half a file, but a failure part-way (a full disk, a permission) leaves the files already moved
    in place. The order limits the damage: output folder first, then the dbt properties, then the deletions, and
    `dbt_project.yml` last. Output files left from an earlier run are not removed.

    When tables are built by dbt, the `model-paths` of `dbt_project.yml` at the repo root (not in `output_dir`, because
    the file is committed) are also brought in step, only if that is needed, and only that key changes. Once any table
    is built by dbt, `dpb generate` owns the whole key: a hand-set entry is replaced. When no table is built by dbt any
    more, only the entries that point at the `models/` folder of a data product are removed.
    The dbt properties files, also committed, are written next to the models. A properties file that carries the
    generated header but is no longer produced (its table is gone or no longer built by dbt) is deleted.

    Args:
        root: The repo root.

    Keyword Args:
        output_dir: The folder to write to. Defaults to the `output_dir` setting, relative to the repo root.

    Raises:
        GenerationError: If a plugin cannot generate a data product, a file cannot be written or deleted, or tables
            are built by dbt and the repo root has no usable `dbt_project.yml`; the message says which.
        PluginNotFoundError: If a plugin is missing. Validation reports that first, so this means a plugin vanished.
    """
    repo, report = load_and_validate(root)
    if not report.ok:
        return GenerateResult(report, (output_dir or root).resolve(), ())
    settings = load_settings(root)
    target = (output_dir or root / settings.values.output_dir).resolve()

    plans = plan_dataproducts(repo, settings)
    files = render_dataproducts(plans, root, target, settings)

    # The dbt properties are committed source files of the repo, not build output, so they go next to the models.
    properties = generate_dbt_properties(plans, settings)
    orphans = orphaned_dbt_properties(repo, properties)

    try:
        dbt_project = synced_dbt_project(repo, settings)
    except DbtProjectError as exc:
        raise GenerationError(str(exc)) from exc

    committed = [generated.path for generated in properties]
    for path, content in files.items():
        _write(target / path, content)
    for generated in properties:
        _write(root / generated.path, generated.content)
    for path in orphans:
        try:
            (root / path).unlink()
        except OSError as exc:
            raise GenerationError(f"cannot delete {root / path}: {exc.strerror or exc}") from exc
    if dbt_project is not None:  # last, so a failed write above leaves the committed file as it was
        _write(dbt_project[0], dbt_project[1])
        committed.append(PurePosixPath(dbt_project[0].relative_to(root).as_posix()))
    return GenerateResult(report, target, tuple(sorted(files)), tuple(committed), tuple(orphans))


def _write(destination: Path, content: str) -> None:
    """Write a file whole or not at all: to a temporary file next to it, then move it into place."""
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(content.encode("utf-8"))
        os.replace(temporary, destination)
    except OSError as exc:
        with contextlib.suppress(OSError):  # best effort: the write error is the one to report
            temporary.unlink(missing_ok=True)
        raise GenerationError(f"cannot write {destination}: {exc.strerror or exc}") from exc
