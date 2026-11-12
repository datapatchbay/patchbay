"""The base model shared by every kind of file."""

from typing import Any

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
