"""The `dpb schema` command."""

import json
from enum import StrEnum
from typing import Annotated

import typer

from datapatchbay.schemas import KINDS, json_schema

Kind = StrEnum("Kind", {kind: kind for kind in KINDS})


def schema(
    kind: Annotated[
        Kind | None,
        typer.Argument(
            help="The kind of file: root (datapatchbay.yaml), dataproduct, port or table. Omit for all four."
        ),
    ] = None,
) -> None:
    """Print the JSON Schema of the files, so an editor or an agent can validate a file before writing it."""
    if kind is None:
        typer.echo(json.dumps({name: json_schema(name) for name in KINDS}, indent=2))
    else:
        typer.echo(json.dumps(json_schema(kind.value), indent=2))
