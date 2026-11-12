from pathlib import Path

import pytest

from datapatchbay.errors import DatapatchbayError
from datapatchbay.loading import load_file
from datapatchbay.models import RootFile
from datapatchbay.settings import DEFAULTS_ORIGIN, ROOT_ORIGIN, defaults_path, load_settings


def write_root(root: Path, text: str) -> None:
    (root / "datapatchbay.yaml").write_text(text)


def test_packaged_defaults_file_passes_the_root_file_schema():
    path = defaults_path()
    model, problems = load_file(path, path.parent, RootFile)
    assert problems == []
    assert model is not None


def test_schema_version_only_file_yields_the_defaults_from_product_md(tmp_path: Path):
    write_root(tmp_path, "schema_version: 1\n")
    settings = load_settings(tmp_path)
    values = settings.values
    assert (values.warehouse, values.orchestrator, values.executor) == ("postgres", "airflow", "python")
    assert (values.runtime, values.severity, values.connection) == ("worker", "error", "warehouse")
    assert {name: kind.prefix for name, kind in values.conventions.kinds.items()} == {
        "source-aligned": "sa",
        "aggregate": "agg",
        "consumer-aligned": "ca",
    }
    assert values.conventions.domains == []
    assert values.conventions.names.model_dump() == {
        "dataproduct": "{kind.prefix}_{name}",
        "output_port": "{kind.prefix}_{name}",
        "private_port": "{kind.prefix}_{name}_private",
        "role": "dp_{kind.prefix}_{name}",
        "dbt_model": "{dataproduct}__{table}",
    }
    assert {entry.origin for entry in settings.entries} == {DEFAULTS_ORIGIN}


def test_single_values_in_repo_file_replace_defaults_and_record_origin(tmp_path: Path):
    write_root(tmp_path, "schema_version: 1\nruntime: docker\n")
    settings = load_settings(tmp_path)
    assert settings.values.runtime == "docker"
    assert settings.origin_of("runtime") == ROOT_ORIGIN
    assert settings.origin_of("warehouse") == DEFAULTS_ORIGIN


def test_maps_merge_key_by_key(tmp_path: Path):
    write_root(
        tmp_path,
        "schema_version: 1\nconventions:\n  kinds:\n    aggregate: {prefix: ag}\n    raw: {prefix: raw}\n"
        "  names:\n    role: 'r_{name}'\n",
    )
    settings = load_settings(tmp_path)
    kinds = {name: kind.prefix for name, kind in settings.values.conventions.kinds.items()}
    assert kinds == {"source-aligned": "sa", "aggregate": "ag", "consumer-aligned": "ca", "raw": "raw"}
    assert settings.origin_of("conventions.kinds.aggregate.prefix") == ROOT_ORIGIN
    assert settings.origin_of("conventions.kinds.raw.prefix") == ROOT_ORIGIN
    assert settings.origin_of("conventions.kinds.source-aligned.prefix") == DEFAULTS_ORIGIN
    assert settings.values.conventions.names.role == "r_{name}"
    assert settings.values.conventions.names.dataproduct == "{kind.prefix}_{name}"


def test_lists_replace_defaults(tmp_path: Path):
    write_root(tmp_path, "schema_version: 1\nconventions:\n  domains: [operations, finance]\n")
    settings = load_settings(tmp_path)
    assert settings.values.conventions.domains == ["operations", "finance"]
    assert settings.origin_of("conventions.domains") == ROOT_ORIGIN


def test_invalid_repo_file_raises_with_file_and_line(tmp_path: Path):
    write_root(tmp_path, "schema_version: 1\nseverity: loud\n")
    with pytest.raises(DatapatchbayError, match=r"datapatchbay\.yaml:2"):
        load_settings(tmp_path)


@pytest.mark.parametrize("text", ["runtime:\n", "conventions:\n", "conventions:\n  domains:\n"])
def test_empty_key_in_repo_file_keeps_the_default(tmp_path: Path, text: str):
    write_root(tmp_path, "schema_version: 1\n" + text)
    settings = load_settings(tmp_path)
    assert {entry.origin for entry in settings.entries} == {DEFAULTS_ORIGIN}
    assert settings.values.runtime == "worker"
    assert settings.values.conventions.domains == []


def test_dbt_project_and_profiles_locations_have_defaults_and_can_be_set(tmp_path: Path):
    write_root(tmp_path, "schema_version: 1\n")
    defaults = load_settings(tmp_path).values.dbt
    assert (defaults.project_dir, defaults.profiles_dir) == (".", "~/.dbt")
    write_root(tmp_path, "schema_version: 1\ndbt:\n  profiles_dir: /etc/dbt\n")
    settings = load_settings(tmp_path)
    assert (settings.values.dbt.project_dir, settings.values.dbt.profiles_dir) == (".", "/etc/dbt")
    assert settings.origin_of("dbt.profiles_dir") == ROOT_ORIGIN
    assert settings.origin_of("dbt.project_dir") == DEFAULTS_ORIGIN


def test_dbt_manifest_location_defaults_to_the_target_folder_and_can_be_set(tmp_path: Path):
    write_root(tmp_path, "schema_version: 1\n")
    assert load_settings(tmp_path).values.dbt.manifest == "target/manifest.json"
    write_root(tmp_path, "schema_version: 1\ndbt:\n  manifest: build/manifest.json\n")
    settings = load_settings(tmp_path)
    assert settings.values.dbt.manifest == "build/manifest.json"
    assert settings.origin_of("dbt.manifest") == ROOT_ORIGIN
