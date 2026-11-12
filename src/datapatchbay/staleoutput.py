"""Finding generated files in the output folder that no data product produces any more."""

from pathlib import Path, PurePosixPath

from datapatchbay.genheader import generated_from
from datapatchbay.plugins import PlannedRepo
from datapatchbay.problems import Problem


def check_stale_output(planned: PlannedRepo) -> list[Problem]:
    """Find files in the output folder whose header names a data product file that does not exist any more.

    Only the files directly in the output folder are looked at, and only those that start with the generated header.
    A hand-written file is left alone. `dpb generate` never deletes output files, so this tells to do it by hand.
    The check is made on the output folder of the settings; a folder given with `dpb generate --output` is not known.

    Returns:
        One problem per stale file, sorted by path.
    """
    repo, settings = planned.repo, planned.settings
    folder = repo.root / settings.values.output_dir
    if not folder.is_dir():
        return []
    sources = {dataproduct.file.path.as_posix() for dataproduct in repo.dataproducts}
    problems = []
    for path in sorted(folder.iterdir()):
        source = generated_from(path) if path.is_file() else None
        if source is not None and source not in sources:
            problems.append(
                Problem(
                    _relative(path, repo.root),
                    None,
                    f"generated file of '{source}', which is not a data product any more; delete it",
                )
            )
    return problems


def _relative(path: Path, root: Path) -> PurePosixPath:
    try:
        return PurePosixPath(path.relative_to(root).as_posix())
    except ValueError:
        return PurePosixPath(path.as_posix())
