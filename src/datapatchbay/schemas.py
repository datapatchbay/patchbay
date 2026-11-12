"""The JSON Schema of the four kinds of file, generated from the models `dpb validate` uses."""

from typing import Any

from pydantic import TypeAdapter

from datapatchbay.models import DataProductFile, PortFile, RootFile, TableFile

KINDS = ("root", "dataproduct", "port", "table")
"""The kinds of file whose schema `dpb schema` prints."""

_DIALECT = "https://json-schema.org/draft/2020-12/schema"

_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "root": TypeAdapter(RootFile),
    "dataproduct": TypeAdapter(DataProductFile),
    "port": TypeAdapter(PortFile),
    "table": TypeAdapter(TableFile),
}
_TITLES = {
    "root": "datapatchbay.yaml",
    "dataproduct": "dataproduct.yaml",
    "port": "port.yaml",
    "table": "table file",
}


def json_schema(kind: str) -> dict[str, Any]:
    """Return the JSON Schema of one kind of file: `root`, `dataproduct`, `port` or `table`."""
    schema = _ADAPTERS[kind].json_schema()
    return {"$schema": _DIALECT, "title": _TITLES[kind], **schema}
