"""The model of `datapatchbay.yaml`."""

from pydantic import BaseModel, ConfigDict, Field

from datapatchbay.models.base import CascadingSettings, FileModel


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KindConvention(_Strict):
    """One data product kind."""

    prefix: str = Field(min_length=1, description="Short prefix that naming templates put in front of derived names.")


class NamesConvention(_Strict):
    """The naming templates (ADR-0006)."""

    dataproduct: str | None = Field(default=None, description="Naming template of the data product folder name.")
    output_port: str | None = Field(default=None, description="Naming template of an output port name.")
    private_port: str | None = Field(default=None, description="Naming template of a private input port name.")
    role: str | None = Field(default=None, description="Naming template of the warehouse role of a data product.")
    dbt_model: str | None = Field(
        default=None,
        description="Naming template of the name of a dbt model, which is also its file name in `models/`. "
        "Besides the usual placeholders it has `{dataproduct}` and `{table}`.",
    )


class Conventions(_Strict):
    """Platform-wide conventions: kinds, domains and naming templates."""

    kinds: dict[str, KindConvention] | None = Field(
        default=None, description="Data product kinds by name, each with the prefix used in derived names."
    )
    domains: list[str] | None = Field(
        default=None, description="Accepted domains. An empty list means any domain is accepted."
    )
    names: NamesConvention | None = Field(default=None, description="Naming templates for derived names.")


class RootFile(FileModel, CascadingSettings):
    """The repo's `datapatchbay.yaml`: settings that apply to all data products.

    Every setting is optional, because defaults ship inside the package and the file only holds the changes.
    """

    warehouse: str | None = Field(default=None, description="Warehouse plugin to generate SQL for.")
    orchestrator: str | None = Field(default=None, description="Orchestrator plugin to generate DAG files for.")
    connection: str | None = Field(default=None, description="Name of the orchestrator's connection to the warehouse.")
    output_dir: str | None = Field(
        default=None,
        min_length=1,
        description="Folder that `dpb generate` writes to, relative to the repo root. `--output` overrides it.",
    )
    conventions: Conventions | None = Field(default=None, description="Platform-wide conventions.")
