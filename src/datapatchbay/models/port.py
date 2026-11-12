"""The models of `port.yaml`, in its three forms."""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from datapatchbay.models.base import CascadingSettings, FileModel

_DURATION = re.compile(r"[1-9][0-9]*[mhd]")

_NAMES = {
    "month": ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
    "weekday": ["sun", "mon", "tue", "wed", "thu", "fri", "sat"],
}
# Name, lowest value, highest value, names accepted instead of numbers.
_CRON_FIELDS = (
    ("minute", 0, 59, ()),
    ("hour", 0, 23, ()),
    ("day of month", 1, 31, ()),
    ("month", 1, 12, _NAMES["month"]),
    ("day of week", 0, 7, _NAMES["weekday"]),
)
_CRON_ATOM = re.compile(r"(?P<first>[0-9]+|[a-z]+)(-(?P<last>[0-9]+|[a-z]+))?")


def _cron_value(text: str, low: int, high: int, names: tuple[str, ...] | list[str], offset: int) -> bool:
    if text.isdigit():
        return low <= int(text) <= high
    return text in names and low <= names.index(text) + offset <= high


def _check_cron_field(text: str, low: int, high: int, names: tuple[str, ...] | list[str]) -> bool:
    offset = 1 if len(names) == 12 else 0
    for part in text.lower().split(","):
        part, _, step = part.partition("/")
        if step and (not step.isdigit() or int(step) == 0):
            return False
        if part == "*":
            continue
        match = _CRON_ATOM.fullmatch(part)
        if match is None:
            return False
        for value in (match["first"], match["last"]):
            if value is not None and not _cron_value(value, low, high, names, offset):
                return False
    return True


def check_duration(value: str) -> str:
    """Accept a duration such as `30m`, `24h` or `7d`."""
    if not _DURATION.fullmatch(value):
        raise ValueError(
            f"'{value}' is not a duration; write a positive whole number and a unit, such as 30m, 24h or 7d"
        )
    return value


def check_cron(value: str) -> str:
    """Accept a five-field cron expression: minute, hour, day of month, month and day of week."""
    fields = value.split()
    if len(fields) != 5:
        raise ValueError(f"'{value}' is not a cron expression; it needs five fields, such as \"0 5 * * *\"")
    for field, (name, low, high, names) in zip(fields, _CRON_FIELDS, strict=True):
        if not _check_cron_field(field, low, high, names):
            raise ValueError(f"'{value}' is not a cron expression; the {name} field '{field}' is not valid")
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
