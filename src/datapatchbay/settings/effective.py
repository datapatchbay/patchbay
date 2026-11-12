"""Effective settings: the packaged defaults merged with the repo's `datapatchbay.yaml`, with the origin of each."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from datapatchbay.errors import DatapatchbayError
from datapatchbay.files.loading import load_root_file
from datapatchbay.files.repo import ROOT_FILE
from datapatchbay.files.repomodel import LoadedFile
from datapatchbay.files.yamlio import load_mapping
from datapatchbay.models import RootFile
from datapatchbay.models.base import Severity
from datapatchbay.models.root import KindConvention
from datapatchbay.settings.pluginsettings import NO_DECLARATIONS, Declarations, installed_declarations

DEFAULTS_ORIGIN = "defaults"
ROOT_ORIGIN = ROOT_FILE

type Origin = str
"""Where a setting comes from: `defaults`, `datapatchbay.yaml`, or `defaults of plugin <name>` (ADR-0025)."""

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


class ResolvedConventions(_Resolved):
    """Platform-wide conventions, all present."""

    kinds: dict[str, KindConvention]
    domains: list[str]
    names: ResolvedNames
    plugin_names: dict[str, str] = Field(default_factory=dict)
    """The naming templates that plugins declare under `conventions.names`, by name (ADR-0025)."""


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
    plugins: Mapping[str, BaseModel] = field(default_factory=dict)
    """The resolved settings section of each plugin that declares one, by plugin name (ADR-0025)."""
    template_placeholders: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    """The extra placeholders of each naming template that a plugin declares, by template name."""

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
    with as_file(files("datapatchbay.settings") / "defaults.yaml") as path:
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


def _with_plugin_defaults(defaults: Mapping[str, Any], declarations: Declarations) -> dict[str, Any]:
    """Add the defaults of plugins: sections come before `conventions`, templates last in `names`."""
    combined: dict[str, Any] = {}
    sections = {section.plugin: dict(section.defaults) for section in declarations.sections}
    templates = {template.name: template.template.default for template in declarations.templates}
    for key, value in defaults.items():
        if key == "conventions":
            combined.update(sections)
            sections = {}
            conventions = dict(value)
            conventions["names"] = {**conventions.get("names", {}), **templates}
            templates = {}
            value = conventions
        combined[key] = value
    combined.update(sections)
    if templates:
        combined["conventions"] = {"names": templates}
    return combined


def _default_origins(declarations: Declarations) -> dict[tuple[str, ...], Origin]:
    """The origin of every default that a plugin declares: the leaves of its section and its naming templates."""
    origins: dict[tuple[str, ...], Origin] = {}
    for section in declarations.sections:
        for path in _leaves(section.defaults, (section.plugin,)):
            origins[path] = f"defaults of plugin {section.plugin}"
    for template in declarations.templates:
        origins[("conventions", "names", template.name)] = f"defaults of plugin {template.plugin}"
    return origins


def merge_settings(
    defaults: Mapping[str, Any], overrides: Mapping[str, Any], declarations: Declarations = NO_DECLARATIONS
) -> EffectiveSettings:
    """Merge a repo's settings over the defaults: maps merge key by key, lists and single values replace.

    Args:
        defaults: The packaged defaults.
        overrides: The repo's `datapatchbay.yaml`.
        declarations: The sections and naming templates that installed plugins declare, with their defaults.
    """
    origins = _default_origins(declarations)
    merged: dict[tuple[str, ...], tuple[Any, Origin]] = {
        path: (value, origins.get(path, "defaults"))
        for path, value in _leaves(_with_plugin_defaults(defaults, declarations)).items()
    }
    merged.update({path: (value, ROOT_ORIGIN) for path, value in _leaves(overrides).items()})
    nested = _nest({path: value for path, (value, _) in merged.items()})
    plugins: dict[str, BaseModel] = {
        section.plugin: section.model.model_validate(nested.pop(section.plugin, {}))
        for section in declarations.sections
    }
    names = nested.get("conventions", {}).get("names", {})
    plugin_names = {template.name: names.pop(template.name) for template in declarations.templates}
    nested.setdefault("conventions", {})["plugin_names"] = plugin_names
    values = ResolvedSettings.model_validate(nested)
    entries = tuple(SettingEntry(path, value, origin) for path, (value, origin) in merged.items())
    placeholders = {template.name: template.template.placeholders for template in declarations.templates}
    return EffectiveSettings(values=values, entries=entries, plugins=plugins, template_placeholders=placeholders)


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
    return merge_settings(load_mapping(defaults_path()), root_file.data, installed_declarations())
