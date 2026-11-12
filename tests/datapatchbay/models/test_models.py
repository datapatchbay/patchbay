import pytest

from datapatchbay.models import (
    DataProductFile,
    DataProductInputPortFile,
    FileModel,
    OutputPortFile,
    RootFile,
    SourceInputPortFile,
    TableFile,
)

ALL_MODELS = [
    RootFile,
    DataProductFile,
    OutputPortFile,
    SourceInputPortFile,
    DataProductInputPortFile,
    TableFile,
]


@pytest.mark.parametrize("model", ALL_MODELS)
def test_models_reject_unknown_keys_and_accept_meta(model: type[FileModel]):
    assert model.model_config["extra"] == "forbid"
    assert "meta" in model.model_json_schema()["properties"]


@pytest.mark.parametrize("model", ALL_MODELS)
def test_every_field_has_a_description_in_the_json_schema(model: type[FileModel]):
    schema = model.model_json_schema()
    for definition in [schema, *schema.get("$defs", {}).values()]:
        for name, prop in definition.get("properties", {}).items():
            assert prop.get("description"), name


def _strict_everywhere(schema: dict) -> bool:
    definitions = [schema, *schema.get("$defs", {}).values()]
    return all(
        d.get("additionalProperties") is False for d in definitions if d.get("type") == "object" and "properties" in d
    )


@pytest.mark.parametrize("model", ALL_MODELS)
def test_every_object_in_the_json_schema_rejects_unknown_keys(model: type[FileModel]):
    assert _strict_everywhere(model.model_json_schema())
