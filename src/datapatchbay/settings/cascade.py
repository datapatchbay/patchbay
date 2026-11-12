"""Resolving the settings over the levels they can be set at: defaults, root, data product, port and table (ADR-0008).

The nearest level wins, and every resolved setting records the level, the file and the line it came from. The
resolution runs once, right after loading: `resolve_cascade` returns a `ResolvedCascade` that the checks, the plans
and `dpb describe` read. The names of the cascading settings are the fields of `CascadingSettings`, so a setting that
cascades the same way, such as a container setting, needs one new field there.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal

from ruamel.yaml.comments import CommentedMap

from datapatchbay.files.repo import ROOT_FILE
from datapatchbay.files.repomodel import DataProduct, LoadedFile, Port, Repo, Table
from datapatchbay.files.yamlio import line_of
from datapatchbay.models.base import CascadingSettings
from datapatchbay.settings.effective import EffectiveSettings

type Level = Literal["table", "port", "dataproduct", "root", "defaults", "unset"]

CASCADING_SETTINGS: tuple[str, ...] = tuple(CascadingSettings.model_fields)
"""The settings that can be set at every level."""

DATAPRODUCT_SETTINGS: tuple[str, ...] = ("orchestrator",)
"""The settings that apply to a whole data product: set on its file or at the root, never on a port or a table."""


@dataclass(frozen=True, slots=True)
class ResolvedSetting:
    """A setting after the cascade.

    Attributes:
        name: The setting, such as `runtime`.
        value: The winning value, or `None` when no level sets it.
        level: The level the value came from; `unset` when no level sets it.
        file: The file that holds the value, relative to the repo root. `None` for the packaged defaults and for
            a setting that is not set.
        line: The 1-based line of the value in `file`. `None` for the packaged defaults and for a setting that is
            not set.
    """

    name: str
    value: Any
    level: Level
    file: PurePosixPath | None
    line: int | None = None

    def to_json(self) -> dict[str, Any]:
        """Return the setting in the public `--json` shape."""
        return {"value": self.value, "level": self.level, "file": str(self.file) if self.file else None}


def _resolve_setting(
    name: str,
    settings: EffectiveSettings,
    *,
    dataproduct: DataProduct | None = None,
    port: Port | None = None,
    table: Table | None = None,
    root_data: CommentedMap | None = None,
) -> ResolvedSetting:
    """Resolve one setting for the place given by the levels below the root.

    Pass the whole chain that leads to the place: a table needs its port and data product, a port its data product.
    A level that is not passed is skipped, so the result is the setting as it holds for that part of the repo.

    Args:
        name: The setting, a field of `CascadingSettings` such as `runtime`, or `orchestrator`.
        settings: The effective settings at the root, which hold the defaults.

    Keyword Args:
        dataproduct: The data product the place belongs to.
        port: The port the place belongs to.
        table: The table the place is.
        root_data: The YAML of `datapatchbay.yaml`, to find the line of a value set at the root.

    Returns:
        The winning value with its level, file and line. A file kind that has no such field, such as a port file for
        `orchestrator`, never sets it, so the setting passes through to the next level.
    """
    layers: list[tuple[Level, LoadedFile[Any], object, tuple[str, ...]]] = []
    if table is not None and table.file.model.build is not None:
        layers.append(("table", table.file, table.file.model.build, ("build", name)))
    if port is not None:
        layers.append(("port", port.file, port.file.model, (name,)))
    if dataproduct is not None:
        layers.append(("dataproduct", dataproduct.file, dataproduct.file.model, (name,)))
    for level, file, model, location in layers:
        value = getattr(model, name, None)
        if value is not None:
            return ResolvedSetting(name, value, level, file.path, file.line(*location))

    for entry in settings.entries:
        if entry.name == name:
            if entry.origin == ROOT_FILE:
                line = None if root_data is None else line_of(root_data, [name])
                return ResolvedSetting(name, entry.value, "root", PurePosixPath(ROOT_FILE), line)
            return ResolvedSetting(name, entry.value, "defaults", None)
    return ResolvedSetting(name, None, "unset", None)


@dataclass(frozen=True, slots=True)
class ResolvedCascade:
    """Every setting resolved for every data product, port and table of a repo, each with its provenance.

    The lookups take the objects of the loaded repo and answer from what `resolve_cascade` computed, so nothing
    resolves a setting a second time.
    """

    dataproducts: Mapping[str, Mapping[str, ResolvedSetting]]
    ports: Mapping[PurePosixPath, Mapping[str, ResolvedSetting]]
    tables: Mapping[PurePosixPath, Mapping[str, ResolvedSetting]]

    def for_dataproduct(self, dataproduct: DataProduct) -> Mapping[str, ResolvedSetting]:
        """The cascading settings at a data product, followed by the settings that only a data product has."""
        return self.dataproducts[dataproduct.folder]

    def for_port(self, port: Port) -> Mapping[str, ResolvedSetting]:
        """The cascading settings as they hold for a port."""
        return self.ports[port.file.path]

    def for_table(self, table: Table) -> Mapping[str, ResolvedSetting]:
        """The cascading settings as they hold for a table."""
        return self.tables[table.file.path]


def resolve_cascade(repo: Repo, settings: EffectiveSettings) -> ResolvedCascade:
    """Resolve every setting once for every data product, port and table of the loaded repo.

    Args:
        repo: What loaded; files that failed validation are not in it, so they are not resolved.
        settings: The effective settings at the root, which hold the defaults.

    Returns:
        The resolved settings, for the places that are looked up by data product, port and table.
    """
    root_data = None if repo.root_file is None else repo.root_file.data
    dataproducts: dict[str, Mapping[str, ResolvedSetting]] = {}
    ports: dict[PurePosixPath, Mapping[str, ResolvedSetting]] = {}
    tables: dict[PurePosixPath, Mapping[str, ResolvedSetting]] = {}
    for dataproduct in repo.dataproducts:
        dataproducts[dataproduct.folder] = {
            name: _resolve_setting(name, settings, dataproduct=dataproduct, root_data=root_data)
            for name in (*CASCADING_SETTINGS, *DATAPRODUCT_SETTINGS)
        }
        for port in dataproduct.ports:
            ports[port.file.path] = {
                name: _resolve_setting(name, settings, dataproduct=dataproduct, port=port, root_data=root_data)
                for name in CASCADING_SETTINGS
            }
            for table in port.tables:
                tables[table.file.path] = {
                    name: _resolve_setting(
                        name, settings, dataproduct=dataproduct, port=port, table=table, root_data=root_data
                    )
                    for name in CASCADING_SETTINGS
                }
    return ResolvedCascade(dataproducts, ports, tables)
