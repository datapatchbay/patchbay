"""Effective settings: the packaged defaults merged with the repo's `datapatchbay.yaml`, with the origin of each."""

from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from datapatchbay.errors import DatapatchbayError
from datapatchbay.loading import load_root_file
from datapatchbay.models import RootFile
from datapatchbay.models.base import Severity
from datapatchbay.models.root import KindConvention
from datapatchbay.repo import ROOT_FILE
from datapatchbay.repomodel import LoadedFile
from datapatchbay.yamlio import load_mapping

DEFAULTS_ORIGIN = "defaults"
ROOT_ORIGIN = ROOT_FILE

type Origin = Literal["defaults", "datapatchbay.yaml"]

# Keys of the root file that are not settings.
_NOT_SETTINGS = frozenset({"schema_version", "meta"})


# Root settings whose value is a map that belongs to a plugin: it is one value, never merged key by key.
_VERBATIM = frozenset({"container"})


class InvalidSettingsError(DatapatchbayError):
    """Raised when the repo's `datapatchbay.yaml` does not pass the root file schema."""


class _Resolved(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResolvedNames(_Resolved):
    """Naming templates, all present."""

    dataproduct: str
    output_port: str
    private_port: str
    role: str
    dbt_model: str


class ResolvedConventions(_Resolved):
    """Platform-wide conventions, all present."""

    kinds: dict[str, KindConvention]
    domains: list[str]
    names: ResolvedNames


class ResolvedDbt(_Resolved):
    """Where dbt finds its project and profile on the worker, and the manifest that `dpb validate` reads."""

    project_dir: str
    profiles_dir: str
    manifest: str


class ResolvedSettings(_Resolved):
    """Every root setting with a value: what later tickets (naming, cascading) read."""

    warehouse: str
    orchestrator: str
    executor: str
    runtime: str
    image: str | None = None
    container: dict[str, Any] | None = None
    severity: Severity
    connection: str
    output_dir: str
    conventions: ResolvedConventions
    dbt: ResolvedDbt


@dataclass(frozen=True, slots=True)
class SettingEntry:
    """One setting: a value (a single value or a list) and the origin it came from.

    Attributes:
        path: The keys leading to the setting, for example `("conventions", "domains")`.
        value: The resolved value.
        origin: `defaults` for the packaged defaults, or `datapatchbay.yaml`.
    """

    path: tuple[str, ...]
    value: Any
    origin: Origin

    @property
    def name(self) -> str:
        """The dotted path of the setting."""
        return ".".join(self.path)


@dataclass(frozen=True, slots=True)
class EffectiveSettings:
    """The settings in effect at the root, typed in `values` and with an origin per setting in `entries`."""

    values: ResolvedSettings
    entries: tuple[SettingEntry, ...]

    def origin_of(self, name: str) -> Origin:
        """Return the origin of a setting given by its dotted path, such as `conventions.domains`.

        Raises:
            KeyError: If there is no such setting.
        """
        for entry in self.entries:
            if entry.name == name:
                return entry.origin
        raise KeyError(name)

    def to_json(self) -> dict[str, Any]:
        """Return the settings in the public `--json` shape: dotted path to `{value, origin}`."""
        return {entry.name: {"value": entry.value, "origin": entry.origin} for entry in self.entries}


def defaults_path() -> Path:
    """Return the path of the packaged defaults file."""
    with as_file(files("datapatchbay") / "defaults.yaml") as path:
        return path


def _leaves(data: Mapping[str, Any], prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], Any]:
    """Flatten nested maps into leaves. A leaf is a single value or a list; lists are never merged."""
    leaves: dict[tuple[str, ...], Any] = {}
    for key, value in data.items():
        if not prefix and key in _NOT_SETTINGS:
            continue
        if value is None:
            continue  # An empty key (`runtime:`) states no value, so the default stays.
        if not prefix and key in _VERBATIM:
            leaves[(key,)] = dict(value)
        elif isinstance(value, Mapping):
            leaves.update(_leaves(value, (*prefix, key)))
        elif isinstance(value, list):
            leaves[(*prefix, key)] = list(value)
        else:
            leaves[(*prefix, key)] = value
    return leaves


def _nest(leaves: Mapping[tuple[str, ...], Any]) -> dict[str, Any]:
    nested: dict[str, Any] = {}
    for path, value in leaves.items():
        node = nested
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = value
    return nested


def merge_settings(defaults: Mapping[str, Any], overrides: Mapping[str, Any]) -> EffectiveSettings:
    """Merge a repo's settings over the defaults: maps merge key by key, lists and single values replace."""
    merged: dict[tuple[str, ...], tuple[Any, Origin]] = {
        path: (value, "defaults") for path, value in _leaves(defaults).items()
    }
    merged.update({path: (value, "datapatchbay.yaml") for path, value in _leaves(overrides).items()})
    values = ResolvedSettings.model_validate(_nest({path: value for path, (value, _) in merged.items()}))
    entries = tuple(SettingEntry(path, value, origin) for path, (value, origin) in merged.items())
    return EffectiveSettings(values=values, entries=entries)


def load_settings(root: Path) -> EffectiveSettings:
    """Resolve the effective settings of the repo at `root`.

    Raises:
        InvalidSettingsError: If `datapatchbay.yaml` is invalid; the message lists every problem with file and line.
    """
    root_file, problems = load_root_file(root)
    if root_file is None:
        raise InvalidSettingsError("\n".join(problem.render() for problem in problems))
    return resolve_settings(root_file)


def resolve_settings(root_file: LoadedFile[RootFile]) -> EffectiveSettings:
    """Resolve the effective settings from a `datapatchbay.yaml` that is already read and valid."""
    return merge_settings(load_mapping(defaults_path()), root_file.data)
