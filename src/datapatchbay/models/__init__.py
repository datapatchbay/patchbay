"""Pydantic models of the files; they are the single source of the validation rules and the JSON Schema."""

from datapatchbay.models.base import SCHEMA_VERSION, FileModel
from datapatchbay.models.dataproduct import DataProductFile
from datapatchbay.models.root import RootFile

__all__ = ["SCHEMA_VERSION", "DataProductFile", "FileModel", "RootFile"]
