"""Reading files against their models and loading a whole repo into memory, one file at a time.

This is per-file schema validation only. Rules that span files live in `crosschecks.py`.
"""

from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Literal, cast

from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails
from ruamel.yaml.comments import CommentedMap

from datapatchbay.files.repo import ROOT_FILE, find_dataproduct_files
from datapatchbay.files.repomodel import DataProduct, LoadedFile, Port, Repo, Table
from datapatchbay.files.yamlio import YamlLoadError, line_of, load_mapping, resolve_location
from datapatchbay.models import (
    PORT_FORMS,
    SCHEMA_VERSION,
    DataProductFile,
    DataProductInputPortFile,
    OutputPortFile,
    PortFile,
    RootFile,
    SourceInputPortFile,
    TableFile,
)
from datapatchbay.problems import Problem

PORT_FILE = "port.yaml"
type Direction = Literal["inputs", "outputs"]
DIRECTIONS: tuple[Direction, ...] = ("inputs", "outputs")

type KeyHint = Callable[[Mapping[str, object], str], str | None]


def relative(path: Path, root: Path) -> PurePosixPath:
    """Return a path relative to the repo root, written with forward slashes."""
    return PurePosixPath(path.relative_to(root).as_posix())


def load_file[M: BaseModel](
    path: Path,
    root: Path,
    model: type[M] | Callable[[Mapping[str, object]], type[M]],
    *,
    key_hint: KeyHint | None = None,
) -> tuple[LoadedFile[M] | None, list[Problem]]:
    """Read one file and validate it against its model, collecting every problem.

    Args:
        path: The file to read.
        root: The repo root, which problem paths are made relative to.
        model: The model of the kind of file, or a function that picks it from the file's content.

    Keyword Args:
        key_hint: Explains an unknown key, when the key is known to belong somewhere else.

    Returns:
        The loaded file, or `None` when there were problems, and the problems found.
    """
    file = relative(path, root)
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

    chosen = cast(type[M], model) if isinstance(model, type) else model(data)
    try:
        return LoadedFile(file, chosen.model_validate(data), data), []
    except ValidationError as exc:
        return None, [_problem(file, data, error, key_hint) for error in exc.errors()]


def _problem(file: PurePosixPath, data: CommentedMap, error: ErrorDetails, key_hint: KeyHint | None) -> Problem:
    kind = error["type"]
    location = resolve_location(data, error["loc"], key_missing=kind == "missing")
    dotted = ".".join(str(part) for part in location)
    if kind == "extra_forbidden":
        hint = key_hint(data, str(location[-1])) if key_hint else None
        message = hint or f"unknown key '{dotted}'; if it is not a typo, it may come from a newer datapatchbay"
    elif kind == "missing" and location == ("schema_version",):
        message = f"missing schema_version; add `schema_version: {SCHEMA_VERSION}`"
    elif kind == "missing":
        message = f"missing required key '{dotted}'"
    elif kind == "unknown_rule":
        given = error["input"]
        name = given.get("rule") if isinstance(given, Mapping) else given
        message = f"{dotted}: {error['msg'].replace(' rule;', f' rule {name!r};')}"
    elif dotted:
        message = f"{dotted}: {error['msg']}"
    else:
        message = error["msg"]
    return Problem(file, line_of(data, location), message)


def load_root_file(root: Path) -> tuple[LoadedFile[RootFile] | None, list[Problem]]:
    """Read `datapatchbay.yaml` against the root file schema; see `load_file`."""
    return load_file(root / ROOT_FILE, root, RootFile)


def _port_model(direction: Direction, data: Mapping[str, object]) -> type[PortFile]:
    if direction == "outputs":
        return OutputPortFile
    return DataProductInputPortFile if "from" in data else SourceInputPortFile


def _orchestrator_hint(data: Mapping[str, object], key: str) -> str | None:
    """Explain `orchestrator` on a port or a table: one data product is one DAG (ADR-0008)."""
    if key == "orchestrator":
        return "orchestrator can only be set in datapatchbay.yaml or dataproduct.yaml: one data product is one DAG"
    return None


def _port_key_hint(direction: Direction) -> KeyHint:
    def hint(data: Mapping[str, object], key: str) -> str | None:
        if (explained := _orchestrator_hint(data, key)) is not None:
            return explained
        this = _port_model(direction, data)
        this_name = next(name for name, form in PORT_FORMS.items() if form is this)
        owners = [name for name, form in PORT_FORMS.items() if form is not this and _has_field(form, key)]
        if not owners:
            return None
        return f"'{key}' belongs to {' or '.join(owners)}, not to {this_name}"

    return hint


def _has_field(model: type[BaseModel], key: str) -> bool:
    return any(key in (name, field.alias) for name, field in model.model_fields.items())


def _load_port(directory: Path, direction: Direction, root: Path) -> tuple[Port | None, list[Problem]]:
    port_path = directory / PORT_FILE
    if not port_path.is_file():
        missing = Problem(relative(port_path, root), None, f"port folder '{directory.name}' has no {PORT_FILE}")
        return None, [missing]

    port_file, problems = load_file(
        port_path,
        root,
        lambda content: _port_model(direction, content),
        key_hint=_port_key_hint(direction),
    )

    table_paths = sorted(p for p in directory.glob("*.yaml") if p.name != PORT_FILE)
    table_files = tuple(relative(p, root) for p in table_paths)
    if port_file is None:
        # Still validate the tables, so one run reports everything.
        for path in table_paths:
            problems.extend(load_file(path, root, TableFile, key_hint=_orchestrator_hint)[1])
        return None, problems

    tables: list[Table] = []
    if not isinstance(port_file.model, DataProductInputPortFile):
        for path in table_paths:
            table_file, table_problems = load_file(path, root, TableFile, key_hint=_orchestrator_hint)
            problems.extend(table_problems)
            if table_file is not None:
                tables.append(Table(table_file))
    port = Port(directory.name, direction, port_file, tuple(tables), table_files)
    return port, problems


def _load_dataproduct(path: Path, root: Path) -> tuple[DataProduct | None, frozenset[str], list[Problem]]:
    directory = path.parent
    dataproduct_file, problems = load_file(path, root, DataProductFile)

    folders: dict[str, tuple[str, ...]] = {}
    ports: dict[str, list[Port]] = {"inputs": [], "outputs": []}
    for direction in DIRECTIONS:
        base = directory / direction
        port_dirs = sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
        folders[direction] = tuple(p.name for p in port_dirs)
        for port_dir in port_dirs:
            port, port_problems = _load_port(port_dir, direction, root)
            problems.extend(port_problems)
            if port is not None:
                ports[direction].append(port)

    if dataproduct_file is None:
        return None, frozenset(folders["outputs"]), problems
    product = DataProduct(
        folder=directory.name,
        directory=directory,
        file=dataproduct_file,
        inputs=tuple(ports["inputs"]),
        outputs=tuple(ports["outputs"]),
        port_folders=folders,
    )
    return product, frozenset(), problems


def load_repo(root: Path) -> tuple[Repo, list[Problem]]:
    """Load every data product under `dataproducts/` and validate each file on its own.

    Every file is read even when an earlier one has problems, so one run reports everything. The returned `Repo`
    holds what loaded; the problems say what did not.
    """
    root_file, problems = load_root_file(root)
    paths = find_dataproduct_files(root)
    repo = Repo(root=root, root_file=root_file, dataproduct_dirs=len(paths))
    unloaded: set[str] = set()
    for path in paths:
        product, unloaded_outputs, product_problems = _load_dataproduct(path, root)
        problems.extend(product_problems)
        unloaded |= unloaded_outputs
        if product is not None:
            repo.dataproducts.append(product)
    repo.unloaded_output_ports = frozenset(unloaded)
    return repo, problems
