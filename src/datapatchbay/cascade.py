"""Resolving a setting over the levels it can be set at: defaults, root, data product, port and table (ADR-0008).

The nearest level wins, and every resolved setting records the level and the file it came from. Settings are looked
up by name, so a setting that cascades the same way, such as a container setting, needs one new field on
`CascadingSettings` and one new entry in `SettingName` and `CASCADING_SETTINGS`.
"""

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal

from datapatchbay.repo import ROOT_FILE
from datapatchbay.repomodel import DataProduct, Port, Table
from datapatchbay.settings import EffectiveSettings

type Level = Literal["table", "port", "dataproduct", "root", "defaults", "unset"]

type SettingName = Literal["executor", "runtime", "image", "severity", "orchestrator"]

CASCADING_SETTINGS: tuple[SettingName, ...] = ("executor", "runtime", "image", "severity")
"""The settings that can be set at every level."""


@dataclass(frozen=True, slots=True)
class ResolvedSetting:
    """A setting after the cascade.

    Attributes:
        name: The setting, such as `runtime`.
        value: The winning value, or `None` when no level sets it.
        level: The level the value came from; `unset` when no level sets it.
        file: The file that holds the value, relative to the repo root. `None` for the packaged defaults and for
            a setting that is not set.
    """

    name: SettingName
    value: Any
    level: Level
    file: PurePosixPath | None

    def to_json(self) -> dict[str, Any]:
        """Return the setting in the public `--json` shape."""
        return {"value": self.value, "level": self.level, "file": str(self.file) if self.file else None}


def resolve_setting(
    name: SettingName,
    settings: EffectiveSettings,
    *,
    dataproduct: DataProduct | None = None,
    port: Port | None = None,
    table: Table | None = None,
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

    Returns:
        The winning value with its level and file. A file kind that has no such field, such as a port file for
        `orchestrator`, never sets it, so the setting passes through to the next level.
    """
    layers: list[tuple[Level, PurePosixPath, object]] = []
    if table is not None and table.file.model.build is not None:
        layers.append(("table", table.file.path, table.file.model.build))
    if port is not None:
        layers.append(("port", port.file.path, port.file.model))
    if dataproduct is not None:
        layers.append(("dataproduct", dataproduct.file.path, dataproduct.file.model))
    for level, file, model in layers:
        value = getattr(model, name, None)
        if value is not None:
            return ResolvedSetting(name, value, level, file)

    for entry in settings.entries:
        if entry.name == name:
            if entry.origin == ROOT_FILE:
                return ResolvedSetting(name, entry.value, "root", PurePosixPath(ROOT_FILE))
            return ResolvedSetting(name, entry.value, "defaults", None)
    return ResolvedSetting(name, None, "unset", None)


def resolve_settings(
    settings: EffectiveSettings,
    *,
    dataproduct: DataProduct | None = None,
    port: Port | None = None,
    table: Table | None = None,
) -> dict[str, ResolvedSetting]:
    """Resolve every cascading setting for a place, keyed by setting name. See `resolve_setting`."""
    return {
        name: resolve_setting(name, settings, dataproduct=dataproduct, port=port, table=table)
        for name in CASCADING_SETTINGS
    }
