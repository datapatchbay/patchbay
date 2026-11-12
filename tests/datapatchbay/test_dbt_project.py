from pathlib import Path

import pytest
from plugin_fakes import FakeOrchestrator, register
from dbt_helpers import DP, MODEL, TABLE_YAML, write

from datapatchbay.generate import GenerationError, generate_repo
from datapatchbay.plugins import UnsupportedCombinationError

PROJECT = "dbt_project.yml"

HEADER = """# the team's dbt project
name: lab   # inline comment
version: "1.0"
profile: lab
model-paths: ["models"]
models:
  lab:
    +materialized: table
"""


@pytest.fixture
def dbt_repo(lab_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # No orchestrator builds dbt tables into a DAG yet, so a fake one stands in; only dbt_project.yml is under test.
    register(monkeypatch, "orchestrator", "fake", FakeOrchestrator)
    (lab_repo / "datapatchbay.yaml").write_text("schema_version: 1\norchestrator: fake\n")
    product = lab_repo / DP / "dataproduct.yaml"
    product.write_text(product.read_text() + "executor: dbt\n")
    write(lab_repo, f"{DP}/outputs/agg_lab_turnaround/turnaround.yaml", TABLE_YAML)
    write(lab_repo, MODEL, "select 1 as days\n")
    write(lab_repo, PROJECT, HEADER)
    return lab_repo


def test_model_paths_lists_the_models_folder_of_each_data_product_with_a_dbt_table(dbt_repo: Path):
    generate_repo(dbt_repo)
    assert f"model-paths: [{DP}/models]" in (dbt_repo / PROJECT).read_text()


def test_model_paths_is_sorted_and_lists_nothing_else(dbt_repo: Path):
    first = "dataproducts/agg_a"
    write(
        dbt_repo,
        f"{first}/dataproduct.yaml",
        "schema_version: 1\nname: a\nkind: aggregate\nowner: Ann\noutputs: [agg_a]\nexecutor: dbt\n",
    )
    write(dbt_repo, f"{first}/outputs/agg_a/port.yaml", "schema_version: 1\nkind: schema\n")
    write(dbt_repo, f"{first}/outputs/agg_a/t.yaml", TABLE_YAML.replace("turnaround", "t"))
    write(dbt_repo, f"{first}/models/agg_a__t.sql", "select 1 as days\n")
    (dbt_repo / PROJECT).write_text(HEADER.replace('["models"]', '["zzz", "models"]'))
    generate_repo(dbt_repo)
    assert f"model-paths: [{first}/models, {DP}/models]" in (dbt_repo / PROJECT).read_text()


def test_comments_key_order_and_other_keys_survive(dbt_repo: Path):
    generate_repo(dbt_repo)
    assert (dbt_repo / PROJECT).read_text() == HEADER.replace('["models"]', f"[{DP}/models]") + (
        f"test-paths:\n  - {DP}/tests\n"
    )


def test_test_paths_keeps_the_style_of_an_existing_list(dbt_repo: Path):
    (dbt_repo / PROJECT).write_text(HEADER + "test-paths: [tests]\n")
    generate_repo(dbt_repo)
    assert f"test-paths: [{DP}/tests]" in (dbt_repo / PROJECT).read_text()


def test_a_repo_without_a_dbt_table_leaves_dbt_project_alone_and_does_not_need_one(lab_repo: Path):
    assert generate_repo(lab_repo).report.ok
    assert not (lab_repo / PROJECT).exists()
    write(lab_repo, PROJECT, HEADER)
    generate_repo(lab_repo)
    assert (lab_repo / PROJECT).read_text() == HEADER


def test_a_dbt_table_without_a_root_dbt_project_fails_naming_where_it_is_expected(dbt_repo: Path):
    (dbt_repo / PROJECT).unlink()
    with pytest.raises(GenerationError, match=r"dbt_project\.yml is expected at the repo root"):
        generate_repo(dbt_repo)
    assert not (dbt_repo / "generated").exists()


def test_the_same_input_gives_byte_identical_output(dbt_repo: Path):
    generate_repo(dbt_repo)
    first = (dbt_repo / PROJECT).read_bytes()
    generate_repo(dbt_repo)
    assert (dbt_repo / PROJECT).read_bytes() == first


def test_a_missing_model_paths_key_is_added_at_the_end(dbt_repo: Path):
    (dbt_repo / PROJECT).write_text("name: lab\nprofile: lab\n")
    generate_repo(dbt_repo)
    assert (dbt_repo / PROJECT).read_text() == (
        f"name: lab\nprofile: lab\nmodel-paths:\n  - {DP}/models\ntest-paths:\n  - {DP}/tests\n"
    )


def test_a_file_already_in_step_is_not_rewritten(dbt_repo: Path):
    (dbt_repo / PROJECT).write_text(HEADER.replace('["models"]', f"[{DP}/models]") + f"test-paths: [{DP}/tests]\n")
    before = (dbt_repo / PROJECT).stat().st_mtime_ns
    generate_repo(dbt_repo)
    assert (dbt_repo / PROJECT).stat().st_mtime_ns == before


def test_a_scalar_model_paths_is_replaced_by_the_list(dbt_repo: Path):
    (dbt_repo / PROJECT).write_text("name: lab\nmodel-paths: models\n")
    generate_repo(dbt_repo)
    assert (
        dbt_repo / PROJECT
    ).read_text() == f"name: lab\nmodel-paths:\n  - {DP}/models\ntest-paths:\n  - {DP}/tests\n"


def test_a_dbt_project_that_is_not_a_mapping_fails_naming_the_file(dbt_repo: Path):
    (dbt_repo / PROJECT).write_text("- just\n- a list\n")
    with pytest.raises(GenerationError, match=r"dbt_project\.yml"):
        generate_repo(dbt_repo)
    assert not (dbt_repo / "generated").exists()


def test_an_invalid_repo_leaves_dbt_project_and_output_alone(dbt_repo: Path):
    (dbt_repo / DP / "dataproduct.yaml").write_text("schema_version: 1\nname: broken\n")
    assert not generate_repo(dbt_repo).report.ok
    assert (dbt_repo / PROJECT).read_text() == HEADER
    assert not (dbt_repo / "generated").exists()


def test_a_failing_orchestrator_leaves_dbt_project_and_output_alone(dbt_repo: Path, monkeypatch: pytest.MonkeyPatch):
    def fail(self, plan, context):
        raise UnsupportedCombinationError("nope")

    monkeypatch.setattr(FakeOrchestrator, "generate", fail)
    with pytest.raises(GenerationError, match="nope"):
        generate_repo(dbt_repo)
    assert (dbt_repo / PROJECT).read_text() == HEADER
    assert not (dbt_repo / "generated").exists()


def test_a_failed_output_write_leaves_dbt_project_as_it_was(dbt_repo: Path):
    (dbt_repo / "generated").write_text("a file where the output folder should be\n")
    with pytest.raises(OSError, match="generated"):
        generate_repo(dbt_repo)
    assert (dbt_repo / PROJECT).read_text() == HEADER


def test_output_option_does_not_move_dbt_project(dbt_repo: Path, tmp_path: Path):
    generate_repo(dbt_repo, output_dir=tmp_path / "out")
    assert not (tmp_path / "out" / PROJECT).exists()
    assert f"{DP}/models" in (dbt_repo / PROJECT).read_text()
