import pytest

from datapatchbay.models import DataProductFile, FileModel, RootFile


@pytest.mark.parametrize("model", [RootFile, DataProductFile])
def test_models_reject_unknown_keys_and_accept_meta(model: type[FileModel]):
    assert model.model_config["extra"] == "forbid"
    assert "meta" in model.model_json_schema()["properties"]


@pytest.mark.parametrize("model", [RootFile, DataProductFile])
def test_every_field_has_a_description_in_the_json_schema(model: type[FileModel]):
    schema = model.model_json_schema()
    for definition in [schema, *schema.get("$defs", {}).values()]:
        for name, prop in definition["properties"].items():
            assert prop.get("description"), name
