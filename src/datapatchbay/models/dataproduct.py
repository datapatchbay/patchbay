"""The model of `dataproduct.yaml`."""

from pydantic import Field

from datapatchbay.models.base import FileModel


class DataProductFile(FileModel):
    """A data product: who owns it and which ports it reads and publishes."""

    name: str = Field(
        min_length=1,
        description="Name of the data product, written without the prefix of its kind. Naming templates derive "
        "the folder name, the port names and the role name from it.",
    )
    kind: str = Field(
        min_length=1,
        description="Data product kind, a label taken from the kinds declared in `datapatchbay.yaml`.",
    )
    owner: str = Field(
        min_length=1,
        description="The person accountable for the data product. Free text, not validated.",
    )
    domain: str | None = Field(
        default=None,
        description="Business area of the data product. Must be one of the declared domains when any are declared.",
    )
    technical_owner: str | None = Field(
        default=None,
        description="The person who builds and maintains the data product. Free text, not validated.",
    )
    description: str | None = Field(default=None, description="What the data product offers, in a sentence or two.")
    inputs: list[str] = Field(
        default_factory=list,
        description="Names of the input ports. Must match the folders under `inputs/`.",
    )
    outputs: list[str] = Field(
        default_factory=list,
        description="Names of the output ports. Must match the folders under `outputs/`.",
    )
