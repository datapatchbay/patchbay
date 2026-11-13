"""The settings that the dbt plugin declares (ADR-0025): the `dbt:` block and the `dbt_model` naming template.

They are written where users always wrote them, in `datapatchbay.yaml`. The core knows nothing about them: it reads the
declaration from the plugin, validates the file with it, shows the values in `dpb config` and hands the resolved block
to the plan.
"""

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from datapatchbay.plugins import DeclaredSettings, NamingTemplate
from datapatchbay.settings.effective import ResolvedConventions

__all__ = [
    "DBT_DECLARED_SETTINGS",
    "DBT_MODEL_TEMPLATE",
    "DbtSettings",
    "ResolvedDbt",
    "dbt_model_template",
    "dbt_settings",
]

DBT_SECTION = "dbt"
"""The key of the settings block: the entry point name of the plugin."""

DBT_MODEL_TEMPLATE = "dbt_model"
"""The name of the naming template of a dbt model under `conventions.names`."""


class DbtSettings(BaseModel):
    """Where dbt finds its project and its profile on the worker, and the manifest `dpb validate` reads."""

    model_config = ConfigDict(extra="forbid")

    project_dir: str | None = Field(
        default=None,
        min_length=1,
        description="The dbt project on the worker. A relative path is relative to the repo root as deployed with the "
        "DAG files.",
    )
    profiles_dir: str | None = Field(
        default=None,
        min_length=1,
        description="The folder with the dbt `profiles.yml` on the worker. `~` is the worker user's home; a relative "
        "path is relative to the dbt project.",
    )
    manifest: str | None = Field(
        default=None,
        min_length=1,
        description="The dbt manifest that `dpb validate` reads, made by `dbt parse`. Relative to the repo root.",
    )


class ResolvedDbt(BaseModel):
    """The `dbt:` block with every value: what the executor and the checks read."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_dir: str
    profiles_dir: str
    manifest: str


DBT_DECLARED_SETTINGS = DeclaredSettings(
    section=DbtSettings,
    description="Where the dbt project and profile are on the worker, for tables built by dbt.",
    defaults={
        "project_dir": ".",  # the dbt project on the worker; relative to the repo root as deployed with the DAG files
        "profiles_dir": "~/.dbt",  # the folder with profiles.yml on the worker; dbt's own default location
        "manifest": "target/manifest.json",  # made by `dbt parse`; `dpb validate` reads it, relative to the repo root
    },
    naming_templates={
        DBT_MODEL_TEMPLATE: NamingTemplate(
            default="{dataproduct}__{table}",
            description="Naming template of the name of a dbt model, which is also its file name in `models/`. "
            "Besides the usual placeholders it has `{dataproduct}` and `{table}`.",
            placeholders=("dataproduct", "table"),
        )
    },
)
"""What the dbt plugin declares."""


def dbt_settings(plugin_settings: Mapping[str, BaseModel]) -> ResolvedDbt:
    """Return the resolved `dbt:` block from the resolved sections of the plugins (`plan.plugin_settings`)."""
    section = plugin_settings.get(DBT_SECTION)
    if section is None:  # the dbt plugin declares the section, so it is resolved whenever dbt is installed
        raise RuntimeError(f"no resolved `{DBT_SECTION}:` section; the dbt plugin's settings were not resolved")
    return ResolvedDbt.model_validate(section.model_dump())


def dbt_model_template(conventions: ResolvedConventions) -> str:
    """Return the `dbt_model` naming template."""
    return conventions.plugin_names[DBT_MODEL_TEMPLATE]
