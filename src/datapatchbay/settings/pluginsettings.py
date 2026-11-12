"""The settings that plugins declare (ADR-0025): a root-level section per plugin and naming templates.

`installed_declarations` asks every installed plugin what it declares and refuses what collides. `root_model` then
extends the model of `datapatchbay.yaml` with the sections and templates, so the file is validated, and its JSON
Schema is generated, with the plugins that are installed. The core never names a plugin.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError, create_model

from datapatchbay.errors import DatapatchbayError
from datapatchbay.models.root import Conventions, NamesConvention, RootFile
from datapatchbay.plugins.interfaces import DeclaresSettings, NamingTemplate
from datapatchbay.plugins.registry import PluginKind, installed_plugins

__all__ = [
    "NO_DECLARATIONS",
    "Declarations",
    "DeclaredSection",
    "DeclaredTemplate",
    "PluginSettingsError",
    "declarations_of",
    "installed_declarations",
    "root_model",
]


class PluginSettingsError(DatapatchbayError):
    """Raised when a plugin declares settings that cannot be added: a collision, or defaults its section rejects."""


@dataclass(frozen=True, slots=True)
class DeclaredSection:
    """The root-level section of one plugin.

    Attributes:
        plugin: The plugin's entry point name, which is also the key in `datapatchbay.yaml`.
        kind: The extension point of the plugin.
        model: The model of the section.
        description: Describes the section in the JSON Schema.
        defaults: The default value of each field.
    """

    plugin: str
    kind: PluginKind
    model: type[BaseModel]
    description: str
    defaults: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class DeclaredTemplate:
    """A naming template that one plugin adds under `conventions.names`."""

    plugin: str
    name: str
    template: NamingTemplate


@dataclass(frozen=True, slots=True)
class Declarations:
    """What the installed plugins declare, in a fixed order: by extension point, then by plugin name."""

    sections: tuple[DeclaredSection, ...] = ()
    templates: tuple[DeclaredTemplate, ...] = ()


NO_DECLARATIONS = Declarations()
"""No plugin declares anything."""


def declarations_of(plugins: Iterable[tuple[PluginKind, str, object]]) -> Declarations:
    """Collect what the given plugins declare and refuse what collides.

    Args:
        plugins: `(kind, name, plugin)` of each plugin. One that does not implement `DeclaresSettings` declares
            nothing.

    Returns:
        The sections and naming templates.

    Raises:
        PluginSettingsError: If a section is named like a core setting or like a section of another plugin, if a
            naming template is named like a core one or like one of another plugin, or if the defaults of a section
            do not pass its model.
    """
    core_keys = set(RootFile.model_fields)
    core_templates = set(NamesConvention.model_fields)
    sections: dict[str, DeclaredSection] = {}
    templates: dict[str, DeclaredTemplate] = {}
    for kind, name, plugin in plugins:
        if not isinstance(plugin, DeclaresSettings):
            continue
        declared = plugin.declared_settings
        if declared.section is not None:
            if name in core_keys:
                raise PluginSettingsError(
                    f"the {kind} plugin '{name}' declares a settings section, but '{name}' is a setting of "
                    "datapatchbay.yaml; rename the plugin"
                )
            if name in sections:
                raise PluginSettingsError(
                    f"the {kind} plugin '{name}' declares a settings section that the {sections[name].kind} plugin "
                    f"'{name}' declares too; rename one of the plugins"
                )
            try:
                declared.section.model_validate(dict(declared.defaults))
            except ValidationError as exc:
                raise PluginSettingsError(
                    f"the defaults of the settings section '{name}' of the {kind} plugin do not pass its model: {exc}"
                ) from exc
            sections[name] = DeclaredSection(name, kind, declared.section, declared.description, declared.defaults)
        for template_name, template in sorted(declared.naming_templates.items()):
            if template_name in core_templates or template_name in templates:
                owner = "a core naming template" if template_name in core_templates else "another plugin"
                raise PluginSettingsError(
                    f"the {kind} plugin '{name}' declares the naming template '{template_name}', which {owner} "
                    "declares too; rename it"
                )
            templates[template_name] = DeclaredTemplate(name, template_name, template)
    return Declarations(tuple(sections.values()), tuple(templates.values()))


def installed_declarations() -> Declarations:
    """Collect what every installed plugin declares; see `declarations_of`."""
    return declarations_of(installed_plugins())


def root_model(declarations: Declarations) -> type[RootFile]:
    """Return the model of `datapatchbay.yaml` extended with the sections and naming templates of the plugins.

    The sections come after the core settings and the templates after the core templates, so without plugins this
    is `RootFile` itself. Every extension is optional, because defaults ship with the plugin.
    """
    if not declarations.sections and not declarations.templates:
        return RootFile
    extensions: dict[str, Any] = {
        section.plugin: (section.model | None, Field(default=None, description=section.description))
        for section in declarations.sections
    }
    if declarations.templates:
        template_fields: dict[str, Any] = {
            template.name: (str | None, Field(default=None, description=template.template.description))
            for template in declarations.templates
        }
        names: Any = create_model(
            NamesConvention.__name__, __base__=NamesConvention, __doc__=NamesConvention.__doc__, **template_fields
        )
        conventions: Any = create_model(
            Conventions.__name__,
            __base__=Conventions,
            __doc__=Conventions.__doc__,
            names=(names | None, Field(default=None, description=Conventions.model_fields["names"].description)),
        )
        extensions["conventions"] = (
            conventions | None,
            Field(default=None, description=RootFile.model_fields["conventions"].description),
        )
    return create_model(RootFile.__name__, __base__=RootFile, __doc__=RootFile.__doc__, **extensions)
