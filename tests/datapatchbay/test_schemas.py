import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel
from ruamel.yaml import YAML

from datapatchbay import models, schemas
from datapatchbay.schemas import Kind

PRODUCT_MD = Path(__file__).parents[2] / "product.md"
# The order of the yaml examples in the section "The schema, version 1" of product.md.
EXAMPLE_KINDS = ["root", "dataproduct", "port", "port", "port", "table"]


def _yaml_examples() -> list[Any]:
    text = PRODUCT_MD.read_text()
    section = text.split("## The schema, version 1", 1)[1].split("## What `dpb validate` enforces", 1)[0]
    return [YAML(typ="safe").load(block) for block in re.findall(r"```yaml\n(.*?)```", section, re.DOTALL)]


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    """Yield every mapping found anywhere inside a JSON Schema."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _file_models() -> list[type[BaseModel]]:
    """Every file model the package exports, so models and fields added later are covered."""
    return [
        value
        for value in vars(models).values()
        if isinstance(value, type) and issubclass(value, models.FileModel) and value is not models.FileModel
    ]


@pytest.mark.parametrize("kind", schemas.KINDS)
def test_each_schema_is_valid_json_schema(kind: Kind):
    Draft202012Validator.check_schema(schemas.json_schema(kind))


def test_the_product_md_examples_are_found():
    assert len(_yaml_examples()) == len(EXAMPLE_KINDS)


@pytest.mark.parametrize(("kind", "example"), list(zip(EXAMPLE_KINDS, _yaml_examples(), strict=True)))
def test_product_md_examples_validate_against_the_printed_schema(kind: Kind, example: Any):
    Draft202012Validator(schemas.json_schema(kind)).validate(example)


@pytest.mark.parametrize(
    ("kind", "bad"),
    [
        ("root", {"schema_version": 1, "colour": "blue"}),
        ("dataproduct", {"schema_version": 1, "name": "x"}),
        ("port", {"schema_version": 1, "kind": "schema", "source": "x"}),
        ("port", {"schema_version": 1, "from": "a", "kind": "schema"}),
        ("table", {"schema_version": 1, "name": "t", "columns": [{"name": "a", "type": "text", "rules": ["nope"]}]}),
        ("table", {"schema_version": 1, "name": "t", "columns": [{"name": "a", "type": "text", "rules": [3]}]}),
    ],
)
def test_the_schema_rejects_invalid_files(kind: Kind, bad: Any):
    assert not Draft202012Validator(schemas.json_schema(kind)).is_valid(bad)


def test_the_schema_accepts_the_bare_rule_short_form_on_columns():
    validator = Draft202012Validator(schemas.json_schema("table"))
    column = {"name": "a", "type": "text", "rules": ["unique", "not_null"]}
    build = {"executor": "python", "entrypoint": "src/t.py:build"}
    assert validator.is_valid({"schema_version": 1, "name": "t", "columns": [column], "build": build})


@pytest.mark.parametrize("kind", schemas.KINDS)
def test_every_property_in_every_schema_has_a_description(kind: Kind):
    for node in _walk(schemas.json_schema(kind)):
        properties = node.get("properties")
        if node.get("type") == "object" and isinstance(properties, dict):
            for name, prop in properties.items():
                assert prop.get("description"), f"{kind}: {name}"


@pytest.mark.parametrize("kind", schemas.KINDS)
def test_every_object_in_every_schema_rejects_unknown_keys(kind: Kind):
    for node in _walk(schemas.json_schema(kind)):
        if node.get("type") == "object" and "properties" in node:
            assert node.get("additionalProperties") is False, f"{kind}: {sorted(node['properties'])}"


@pytest.mark.parametrize("model", _file_models(), ids=lambda m: m.__qualname__)
def test_every_model_field_is_in_its_schema_with_a_description(model: type[BaseModel]):
    schema = model.model_json_schema()
    for name, info in model.model_fields.items():
        key = info.alias or name
        assert key in schema["properties"], f"{model.__qualname__}.{name}"
        assert schema["properties"][key].get("description"), f"{model.__qualname__}.{name}"


def test_the_file_models_are_found():
    assert len(_file_models()) >= 6


@pytest.mark.parametrize(
    ("kind", "file"),
    [
        ("root", {"schema_version": 1, "executor": "python", "runtime": "docker", "image": "x:1", "severity": "none"}),
        ("dataproduct", {"schema_version": 1, "name": "x", "kind": "k", "owner": "o", "runtime": "any-plugin"}),
        ("table", {"schema_version": 1, "name": "t", "build": {"entrypoint": "src/t.py:b", "image": "x:2"}}),
    ],
)
def test_the_schema_accepts_cascading_settings_at_every_level(kind: Kind, file: Any):
    errors = Draft202012Validator(schemas.json_schema(kind)).iter_errors(file)
    assert not [e.message for e in errors if any(w in e.message for w in ("executor", "runtime", "image"))]


def test_the_schema_rejects_orchestrator_on_a_table_build_block():
    build = {"entrypoint": "src/t.py:b", "orchestrator": "prefect"}
    assert not Draft202012Validator(schemas.json_schema("table")).is_valid(
        {"schema_version": 1, "name": "t", "build": build}
    )
