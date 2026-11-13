"""The JSON Schema of the four kinds of file, generated from the models `dpb validate` uses."""

from typing import Any, Literal

from pydantic import TypeAdapter

from datapatchbay.models import DataProductFile, PortFile, TableFile
from datapatchbay.settings.pluginsettings import installed_declarations, root_model

Kind = Literal["root", "dataproduct", "port", "table"]
"""A kind of file whose schema `dpb schema` prints."""

KINDS: tuple[Kind, ...] = ("root", "dataproduct", "port", "table")
"""The kinds of file whose schema `dpb schema` prints."""

_DIALECT = "https://json-schema.org/draft/2020-12/schema"

_ADAPTERS: dict[Kind, TypeAdapter[Any]] = {
    "dataproduct": TypeAdapter(DataProductFile),
    "port": TypeAdapter(PortFile),
    "table": TypeAdapter(TableFile),
}
_TITLES: dict[Kind, str] = {
    "root": "datapatchbay.yaml",
    "dataproduct": "dataproduct.yaml",
    "port": "port.yaml",
    "table": "table file",
}


def json_schema(kind: Kind) -> dict[str, Any]:
    """Return the JSON Schema of one kind of file.

    Args:
        kind: The kind of file: `root`, `dataproduct`, `port` or `table`.

    Returns:
        The schema, with `$schema` and a `title` added. The schema of `root` includes the sections and naming
        templates that installed plugins declare (ADR-0025).
    """
    adapter = TypeAdapter(root_model(installed_declarations())) if kind == "root" else _ADAPTERS[kind]
    schema = adapter.json_schema()
    return {"$schema": _DIALECT, "title": _TITLES[kind], **schema}
