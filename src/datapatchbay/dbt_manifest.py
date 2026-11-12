"""Checking what dbt models read, against the input ports of their data product (ADR-0014, ADR-0018).

The reads come from the dbt manifest that the team's `dbt parse` writes, read as plain JSON; nothing here imports or
runs dbt (ADR-0004). Only these fields are used, and every other field is ignored, so a newer manifest schema keeps
working as long as they stay (checked against schema v12, https://schemas.getdbt.com/dbt/manifest/v12.json):

- `metadata.project_name`: models of other dbt packages are not the team's.
- `nodes.<id>`: `resource_type`, `name`, `package_name`, `original_file_path`, `depends_on.nodes`.
- `sources.<id>`: `source_name`, `name`, `schema`.

A model belongs to the data product whose folder holds its file. The rules live here, not in the dbt executor, so a
later executor that reports its reads gets the same checks.
"""

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from datapatchbay.dbt_project import model_paths
from datapatchbay.planning import PlannedRepo
from datapatchbay.problems import Problem
from datapatchbay.repomodel import DataProduct, Repo


class _ManifestError(ValueError):
    """The manifest is missing a field that this check needs."""


@dataclass(frozen=True, slots=True)
class _Model:
    name: str
    file: PurePosixPath
    depends_on: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Source:
    port: str
    table: str
    schema: str | None


@dataclass(frozen=True, slots=True)
class _Manifest:
    models: dict[str, _Model]  # nodes by unique id: the models that can read, and the ones that can be read
    sources: dict[str, _Source]
    readers: tuple[str, ...]  # unique ids of the team's models, sorted


def check_dbt_reads(planned: PlannedRepo) -> list[Problem]:
    """Compare what each dbt model reads with the input ports of its data product.

    Fails a model that `ref()`s a model of another data product (a read of its private schema), and a model that
    reads the `source()` of another data product's output port, or the private schema of another data product,
    without an input port on it. A source that is no output port of the repo is not a read of a data product and is
    not checked, and neither is a table name written into the SQL (ADR-0014, ADR-0018). That a reading data product
    may have an input port on an output port at all (its readers, ADR-0007) is checked when the input ports are.

    Args:
        planned: The repo that passed the gate. Its settings say where the manifest is (`dbt.manifest`).

    Returns:
        The problems found, empty when no table is built by dbt or every read is allowed. A missing, unreadable or
        incomplete manifest is one problem on the manifest file.
    """
    repo, settings = planned.repo, planned.settings
    if not model_paths(repo, settings):
        return []
    setting = settings.values.dbt.manifest
    location = PurePosixPath(Path(setting).as_posix())
    path = Path(setting) if Path(setting).is_absolute() else repo.root / setting
    if not path.is_file():
        return [
            Problem(
                location,
                None,
                "dbt manifest not found, but tables are built by dbt; run `dbt parse` or set `dbt.manifest`",
            )
        ]
    try:
        manifest = _read(path)
    except (OSError, ValueError) as exc:  # ValueError covers bad JSON and _ManifestError
        return [Problem(location, None, f"dbt manifest cannot be read ({exc}); run `dbt parse` again")]
    # In file and line order, so the report does not depend on the order of the manifest.
    return sorted(_check(repo, manifest), key=lambda problem: (str(problem.file), problem.line or 0, problem.message))


def _read(path: Path) -> _Manifest:
    document = json.loads(path.read_text(encoding="utf-8"))
    nodes = _mapping(document, "nodes")
    project = _mapping(document, "metadata", required=False).get("project_name")
    models: dict[str, _Model] = {}
    for unique_id, node in nodes.items():
        if not isinstance(node, dict) or node.get("resource_type") not in {"model", "snapshot", "seed"}:
            continue
        if project is not None and node.get("package_name") != project:
            continue
        file = node.get("original_file_path")
        name = node.get("name")
        if not isinstance(file, str) or not isinstance(name, str):
            raise _ManifestError(f"node '{unique_id}' has no `original_file_path` and `name`")
        depends = _mapping(node, "depends_on", required=False).get("nodes", [])
        if not isinstance(depends, list):
            raise _ManifestError(f"`depends_on.nodes` of node '{unique_id}' is not a list")
        models[unique_id] = _Model(name, PurePosixPath(file.replace("\\", "/")), tuple(map(str, depends)))
    sources: dict[str, _Source] = {}
    for unique_id, source in _mapping(document, "sources", required=False).items():
        if isinstance(source, dict) and isinstance(source.get("source_name"), str):
            schema = source.get("schema")
            sources[unique_id] = _Source(
                source["source_name"], str(source.get("name")), schema if isinstance(schema, str) else None
            )
    readers = tuple(
        sorted(
            unique_id for unique_id, node in nodes.items() if unique_id in models and node["resource_type"] == "model"
        )
    )
    return _Manifest(models, sources, readers)


def _mapping(parent: Any, key: str, *, required: bool = True) -> Mapping[str, Any]:
    value = parent.get(key) if isinstance(parent, dict) else None
    if isinstance(value, dict):
        return value
    if required:
        raise _ManifestError(f"no `{key}` map")
    return {}


def _check(repo: Repo, manifest: _Manifest) -> Iterator[Problem]:
    owners = sorted(
        ((dataproduct.directory.relative_to(repo.root).as_posix(), dataproduct) for dataproduct in repo.dataproducts),
        key=lambda item: -len(item[0]),
    )
    outputs = {port.name: dataproduct for dataproduct in repo.dataproducts for port in dataproduct.outputs}
    privates = {
        port.name: dataproduct
        for dataproduct in repo.dataproducts
        for port in dataproduct.inputs
        if port.reads_port is None
    }

    def owner_of(file: PurePosixPath) -> DataProduct | None:
        return next((product for folder, product in owners if file.as_posix().startswith(f"{folder}/")), None)

    for unique_id in manifest.readers:
        model = manifest.models[unique_id]
        reader = owner_of(model.file)
        if reader is None:
            continue  # a model outside the data product folders is not a data product's build code
        allowed = {port.reads_port for port in reader.inputs if port.reads_port is not None}
        for dependency in model.depends_on:
            target = manifest.models.get(dependency)
            if target is not None:
                producer = owner_of(target.file)
                if producer is not None and producer is not reader:
                    yield _problem(
                        repo,
                        model,
                        _pattern_ref(target.name),
                        f"model '{model.name}' of data product '{reader.folder}' reads model '{target.name}' of data "
                        f"product '{producer.folder}' with `ref()`, which is a read of its private schema; read an "
                        "output port through an input port and `source()` instead (ADR-0018)",
                    )
                continue
            source = manifest.sources.get(dependency)
            if source is None:
                continue
            producer = outputs.get(source.port)
            if producer is not None and producer is not reader and source.port not in allowed:
                yield _problem(
                    repo,
                    model,
                    _pattern_source(source),
                    f"model '{model.name}' of data product '{reader.folder}' reads source '{source.port}', the "
                    f"output port of data product '{producer.folder}', but '{reader.folder}' has no input port on "
                    f"'{source.port}' (ADR-0014)",
                )
            private = privates.get(source.schema or "")
            if private is not None and private is not reader:
                yield _problem(
                    repo,
                    model,
                    _pattern_source(source),
                    f"model '{model.name}' of data product '{reader.folder}' reads source '{source.port}', which "
                    f"points at the private schema '{source.schema}' of data product '{private.folder}'",
                )


def _pattern_ref(name: str) -> re.Pattern[str]:
    return re.compile(rf"""\bref\(\s*(?:['"][^'"]*['"]\s*,\s*)?['"]{re.escape(name)}['"]""")


def _pattern_source(source: _Source) -> re.Pattern[str]:
    return re.compile(rf"""\bsource\(\s*['"]{re.escape(source.port)}['"]\s*,\s*['"]{re.escape(source.table)}['"]""")


def _problem(repo: Repo, model: _Model, pattern: re.Pattern[str], message: str) -> Problem:
    """Point a problem at the line of the model file that makes the read, or at the file when it cannot be found."""
    line = None
    try:
        lines = (repo.root / model.file).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        lines = []  # the file is still reported; only its line is unknown
    for number, text in enumerate(lines, start=1):
        if pattern.search(text):
            line = number
            break
    return Problem(model.file, line, message)
