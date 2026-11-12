"""The `dpb schema` command."""

import json
from enum import StrEnum
from typing import Annotated, cast

import typer

from datapatchbay.commands.schemas import KINDS, Kind, json_schema

_Kind = StrEnum("_Kind", {kind: kind for kind in KINDS})


def schema(
    kind: Annotated[
        _Kind | None,
        typer.Argument(
            help="The kind of file: root (datapatchbay.yaml), dataproduct, port or table. Omit for all four."
        ),
    ] = None,
) -> None:
    """Print the JSON Schema of the files, so an editor or an agent can validate a file before writing it."""
    if kind is None:
        typer.echo(json.dumps({name: json_schema(name) for name in KINDS}, indent=2))
    else:
        typer.echo(json.dumps(json_schema(cast(Kind, kind.value)), indent=2))
