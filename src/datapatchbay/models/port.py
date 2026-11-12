"""The models of `port.yaml`, in its three forms."""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from datapatchbay.models.base import CascadingSettings, FileModel
from datapatchbay.models.schedule import CRON_FIELDS, DURATION, is_valid_cron_field


def check_duration(value: str) -> str:
    """Accept a duration such as `30m`, `24h` or `7d`."""
    if not DURATION.fullmatch(value):
        raise ValueError(
            f"'{value}' is not a duration; write a positive whole number and a unit, such as 30m, 24h or 7d"
        )
    return value


def check_cron(value: str) -> str:
    """Accept a five-field cron expression: minute, hour, day of month, month and day of week."""
    fields = value.split()
    if len(fields) != 5:
        raise ValueError(f"'{value}' is not a cron expression; it needs five fields, such as \"0 5 * * *\"")
    for text, field in zip(fields, CRON_FIELDS, strict=True):
        if not is_valid_cron_field(text, field):
            raise ValueError(f"'{value}' is not a cron expression; the {field.name} field '{text}' is not valid")
    return value


Duration = Annotated[
    str,
    AfterValidator(check_duration),
    Field(
        json_schema_extra={"pattern": "^[1-9][0-9]*[mhd]$"},
        description="A duration: a positive whole number and a unit of m (minutes), h (hours) or d (days).",
        examples=["30m", "24h", "7d"],
    ),
]
CronExpression = Annotated[
    str,
    AfterValidator(check_cron),
    Field(description="A five-field cron expression: minute, hour, day of month, month, day of week."),
]


class ProductReader(BaseModel):
    """A data product that may read an output port."""

    model_config = ConfigDict(extra="forbid")

    product: str = Field(
        min_length=1,
        description="Folder name of the data product. It maps to that data product's warehouse role.",
    )


class Access(BaseModel):
    """Who may read an output port."""

    model_config = ConfigDict(extra="forbid")

    readers: list[str | ProductReader] = Field(
        default_factory=list,
        description="Readers of the output port. A plain string is a warehouse role name used as written; "
        "`product: <data product>` maps to that data product's role.",
    )
    pii_readers: list[str] = Field(
        default_factory=list,
        description="Readers that also see the columns marked `pii`. Everyone else sees NULL in those columns.",
    )


class OutputPortFile(FileModel, CascadingSettings):
    """An output port: what a data product publishes, with its freshness promise and access policy."""

    kind: Literal["schema", "table"] = Field(
        description="Port kind. A `schema` port holds any number of table files; a `table` port holds exactly one."
    )
    freshness: Duration | None = Field(
        default=None,
        description="How old the newest data in this output port may be. Without it, the port is not checked.",
    )
    access: Access = Field(default_factory=Access, description="Who may read this output port.")


class SourceInputPortFile(FileModel, CascadingSettings):
    """An input port fed by a source outside the platform."""

    kind: Literal["schema", "table"] = Field(
        description="Port kind. A `schema` port holds any number of table files; a `table` port holds exactly one."
    )
    source: str = Field(min_length=1, description="The source that delivers data into this input port. Free text.")
    schedule: CronExpression = Field(
        description="When the source delivers data, as a cron expression. The orchestrator runs it; dpb does not."
    )


class DataProductInputPortFile(FileModel):
    """An input port that reads the output port of another data product. It has no table files."""

    from_: str = Field(
        alias="from",
        min_length=1,
        description="Name of the output port, of another data product, that this input port reads.",
    )


type PortFile = OutputPortFile | SourceInputPortFile | DataProductInputPortFile
"""Any of the three forms of `port.yaml`."""

PORT_FORMS: dict[str, type[FileModel]] = {
    "an output port": OutputPortFile,
    "an input port fed by a source": SourceInputPortFile,
    "an input port that reads another data product": DataProductInputPortFile,
}
