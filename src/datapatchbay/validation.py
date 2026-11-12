"""Validating files against their models and a whole repo against the schema."""

from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ValidationError

from datapatchbay.models import SCHEMA_VERSION, DataProductFile, RootFile
from datapatchbay.problems import Problem, Report
from datapatchbay.repo import ROOT_FILE, find_dataproduct_files
from datapatchbay.yamlio import YamlLoadError, line_of, load_mapping


def validate_file[M: BaseModel](path: Path, root: Path, model: type[M]) -> tuple[M | None, list[Problem]]:
    """Validate one file against its model, collecting every problem.

    Args:
        path: The file to read.
        root: The repo root, which problem paths are made relative to.
        model: The model of the kind of file.

    Returns:
        The validated model, or `None` when there were problems, and the problems found.
    """
    file = PurePosixPath(path.relative_to(root).as_posix())
    try:
        data = load_mapping(path)
    except YamlLoadError as exc:
        return None, [Problem(file, exc.line, str(exc))]

    version = data.get("schema_version")
    if isinstance(version, int) and not isinstance(version, bool) and version > SCHEMA_VERSION:
        line = line_of(data, ["schema_version"])
        message = (
            f"schema_version {version} is newer than this datapatchbay understands "
            f"(newest known: {SCHEMA_VERSION}); upgrade datapatchbay"
        )
        return None, [Problem(file, line, message)]

    try:
        return model.model_validate(data), []
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            location = error["loc"]
            dotted = ".".join(str(part) for part in location)
            if error["type"] == "extra_forbidden":
                message = f"unknown key '{dotted}'; if it is not a typo, it may come from a newer datapatchbay"
            elif error["type"] == "missing" and location == ("schema_version",):
                message = f"missing schema_version; add `schema_version: {SCHEMA_VERSION}`"
            elif error["type"] == "missing":
                message = f"missing required key '{dotted}'"
            else:
                message = f"{dotted}: {error['msg']}"
            problems.append(Problem(file, line_of(data, location), message))
        return None, problems


def validate_repo(root: Path) -> Report:
    """Validate `datapatchbay.yaml` and every `dataproduct.yaml` under `dataproducts/`.

    Every file is checked even when an earlier one has problems, so one run reports everything.
    """
    _, problems = validate_file(root / ROOT_FILE, root, RootFile)
    files = find_dataproduct_files(root)
    for path in files:
        _, file_problems = validate_file(path, root, DataProductFile)
        problems.extend(file_problems)
    return Report(dataproducts_checked=len(files), problems=problems)
