"""The base model shared by every kind of file."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1
"""The newest `schema_version` this release understands."""


class FileModel(BaseModel):
    """Base of the four kinds of file: strict keys, a `schema_version` and a free-form `meta` map (ADR-0011)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(
        ge=1,
        le=SCHEMA_VERSION,
        strict=True,
        description="Version of the datapatchbay schema this file follows. It goes up only for breaking changes.",
    )
    meta: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form map for a team's own extras. datapatchbay never reads it.",
    )


Severity = Literal["error", "warning", "none"]


class CascadingSettings(BaseModel):
    """Settings that can be set at the root, on a data product, on a port and in a table's build block (ADR-0008).

    The nearest one wins; `datapatchbay.cascade` resolves them. `executor` and `runtime` name plugins (ADR-0009), so
    they accept any non-empty name here and the plugin check happens where the plugins are known.
    """

    model_config = ConfigDict(extra="forbid")

    executor: str | None = Field(
        default=None, min_length=1, description="Executor plugin that builds the tables. The nearest level wins."
    )
    runtime: str | None = Field(
        default=None,
        min_length=1,
        description="Runtime plugin that runs the build code, such as `worker`, `docker` or `kubernetes`. "
        "The nearest level wins.",
    )
    image: str | None = Field(
        default=None,
        min_length=1,
        description="Container image the build code runs in, for container runtimes. The nearest level wins.",
    )
    container: dict[str, Any] | None = Field(
        default=None,
        min_length=1,
        description="Free-form settings handed as written to the container task of a container runtime, such as "
        "environment variables or secrets. dpb does not read them. The nearest level wins, as a whole.",
    )
    severity: Severity | None = Field(
        default=None,
        description="Default severity of quality rules: `error` fails the run, `warning` reports and continues, "
        "`none` ignores the rule. The nearest level wins.",
    )
