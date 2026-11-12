from pathlib import Path

import pytest
from dbt_helpers import DP, MODEL, TABLE_YAML, rendered, write
from plugin_fakes import FakeOrchestrator, register

from datapatchbay.generate import generate_repo

PROJECT = "dbt_project.yml"
PROPERTIES = f"{DP}/models/agg_lab_turnaround__turnaround.yml"
GROUP = f"{DP}/models/_group.yml"
SOURCES = f"{DP}/models/_sources.yml"


@pytest.fixture
def synced_repo(lab_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    register(monkeypatch, "orchestrator", "fake", FakeOrchestrator)
    (lab_repo / "datapatchbay.yaml").write_text("schema_version: 1\norchestrator: fake\n")
    product = lab_repo / DP / "dataproduct.yaml"
    product.write_text(product.read_text() + "executor: dbt\n")
    write(lab_repo, f"{DP}/outputs/agg_lab_turnaround/turnaround.yaml", TABLE_YAML)
    write(lab_repo, MODEL, "select 1 as days\n")
    write(lab_repo, PROJECT, "name: lab\nversion: '1.0'\nprofile: lab\n")
    generate_repo(lab_repo)
    return lab_repo


def snapshot(repo: Path) -> dict[str, bytes]:
    return {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}


def test_files_made_by_generate_pass(synced_repo: Path):
    assert rendered(synced_repo) == []


def test_a_repo_without_dbt_tables_needs_nothing(lab_repo: Path):
    assert rendered(lab_repo) == []


def test_a_changed_table_file_makes_the_properties_stale(synced_repo: Path):
    table = synced_repo / DP / "outputs/agg_lab_turnaround/turnaround.yaml"
    table.write_text(table.read_text() + "  - name: extra\n    type: text\n")
    problems = rendered(synced_repo)
    assert len(problems) == 1
    assert problems[0].startswith(f"{PROPERTIES}: ")
    assert "dpb generate" in problems[0]


def test_hand_edited_properties_fail(synced_repo: Path):
    (synced_repo / PROPERTIES).write_text("models: []\n")
    assert any(p.startswith(f"{PROPERTIES}: ") and "dpb generate" in p for p in rendered(synced_repo))


def test_a_missing_properties_file_fails(synced_repo: Path):
    (synced_repo / GROUP).unlink()
    problems = rendered(synced_repo)
    assert len(problems) == 1
    assert problems[0].startswith(f"{GROUP}: ")
    assert "missing" in problems[0]
    assert "dpb generate" in problems[0]


def test_stale_model_paths_fail(synced_repo: Path):
    (synced_repo / PROJECT).write_text("name: lab\nversion: '1.0'\nprofile: lab\nmodel-paths: [models]\n")
    problems = rendered(synced_repo)
    assert len(problems) == 1
    assert problems[0].startswith(f"{PROJECT}: ")
    assert "model-paths" in problems[0]
    assert "dpb generate" in problems[0]


def test_a_missing_dbt_project_fails(synced_repo: Path):
    (synced_repo / PROJECT).unlink()
    assert any(p.startswith(f"{PROJECT}: ") for p in rendered(synced_repo))


@pytest.mark.parametrize("location", [f"{DP}/models/extra.yml", f"{DP}/models/sub/more.yaml"])
def test_a_hand_written_entry_for_a_built_model_is_a_duplicate(synced_repo: Path, location: str):
    write(synced_repo, location, "models:\n  - name: other\n  - name: agg_lab_turnaround__turnaround\n")
    problems = rendered(synced_repo)
    assert len(problems) == 1
    assert problems[0].startswith(f"{location}:3: ")
    assert "agg_lab_turnaround__turnaround" in problems[0]
    assert PROPERTIES in problems[0]


def test_other_models_in_other_files_are_fine(synced_repo: Path):
    write(synced_repo, f"{DP}/models/extra.yml", "models:\n  - name: hand_made\nsources:\n  - name: raw\n")
    write(synced_repo, f"{DP}/models/notes.yml", "- just a list\n")
    assert rendered(synced_repo) == []


def test_validate_writes_nothing(synced_repo: Path):
    (synced_repo / PROPERTIES).write_text("stale\n")
    write(synced_repo, f"{DP}/models/extra.yml", "models:\n  - name: agg_lab_turnaround__turnaround\n")
    before = snapshot(synced_repo)
    assert rendered(synced_repo)
    assert snapshot(synced_repo) == before


def test_generate_still_repairs_stale_files(synced_repo: Path):
    (synced_repo / PROPERTIES).write_text("stale\n")
    assert generate_repo(synced_repo).report.ok
    assert rendered(synced_repo) == []


def _remove_the_dbt_table(repo: Path) -> None:
    """The table stays but python builds it, so dbt builds no table and the generated files are left behind."""
    table = repo / DP / "outputs/agg_lab_turnaround/turnaround.yaml"
    table.write_text(table.read_text() + "build:\n  entrypoint: src/turnaround.py:build\n")
    write(repo, f"{DP}/src/turnaround.py", "def build():\n    pass\n")
    (repo / MODEL).unlink()
    product = repo / DP / "dataproduct.yaml"
    product.write_text(product.read_text().replace("executor: dbt\n", ""))


def test_orphaned_generated_properties_fail_with_a_message_to_delete_them(synced_repo: Path):
    _remove_the_dbt_table(synced_repo)
    problems = rendered(synced_repo)
    assert any(p.startswith(f"{PROPERTIES}: ") and "delete it" in p for p in problems)
    assert any(p.startswith(f"{GROUP}: ") and "delete it" in p for p in problems)


def test_a_hand_written_properties_file_is_not_an_orphan(synced_repo: Path):
    write(synced_repo, f"{DP}/models/extra.yml", "models:\n  - name: hand_made\n")
    assert rendered(synced_repo) == []


def test_generate_deletes_orphaned_generated_properties_and_stale_model_paths(synced_repo: Path):
    write(synced_repo, f"{DP}/models/extra.yml", "models:\n  - name: hand_made\n")
    _remove_the_dbt_table(synced_repo)
    result = generate_repo(synced_repo)
    assert result.report.ok
    assert not (synced_repo / PROPERTIES).exists()
    assert not (synced_repo / GROUP).exists()
    assert (synced_repo / DP / "models/extra.yml").exists()  # hand-written, so left alone
    assert sorted(path.as_posix() for path in result.removed) == [GROUP, SOURCES, PROPERTIES]
    assert "model-paths" not in (synced_repo / PROJECT).read_text()
    assert rendered(synced_repo) == []


def test_stale_model_paths_of_data_products_fail_when_no_table_is_built_by_dbt(synced_repo: Path):
    _remove_the_dbt_table(synced_repo)
    (synced_repo / PROPERTIES).unlink()
    (synced_repo / GROUP).unlink()
    (synced_repo / SOURCES).unlink()
    problems = rendered(synced_repo)
    assert len(problems) == 1
    assert problems[0].startswith(f"{PROJECT}: ")
    assert "model-paths" in problems[0]


def test_other_model_paths_survive_when_no_table_is_built_by_dbt(synced_repo: Path):
    _remove_the_dbt_table(synced_repo)
    (synced_repo / PROJECT).write_text(f"name: lab\nversion: '1.0'\nmodel-paths: [models, {DP}/models]\n")
    generate_repo(synced_repo)
    assert "model-paths: [models]" in (synced_repo / PROJECT).read_text()


def test_generate_lists_the_repo_files_it_wrote(synced_repo: Path):
    (synced_repo / PROPERTIES).write_text("stale\n")
    (synced_repo / PROJECT).write_text("name: lab\nversion: '1.0'\nprofile: lab\n")
    result = generate_repo(synced_repo)
    assert [path.as_posix() for path in result.committed] == [GROUP, SOURCES, PROPERTIES, PROJECT]


TURNAROUND = f"{DP}/outputs/agg_lab_turnaround/turnaround.yaml"
TEST_FILE = f"{DP}/tests/agg_lab_turnaround__turnaround__row_count.sql"


@pytest.fixture
def tested_repo(synced_repo: Path) -> Path:
    """A repo in step whose dbt table has a table rule, so a generated singular test exists."""
    write(synced_repo, TURNAROUND, TABLE_YAML + "rules:\n  - {rule: row_count, min: 1}\n")
    generate_repo(synced_repo)
    assert (synced_repo / TEST_FILE).is_file()
    assert rendered(synced_repo) == []
    return synced_repo


def test_a_generated_test_whose_table_is_no_longer_built_by_dbt_is_an_orphan(tested_repo: Path):
    # The tests/ folder drops out of test-paths here, and the scan must still look at it.
    _remove_the_dbt_table(tested_repo)
    problems = rendered(tested_repo)
    assert any(p.startswith(f"{TEST_FILE}: ") and "delete it" in p for p in problems)


def test_a_generated_test_whose_rule_was_removed_is_an_orphan(tested_repo: Path):
    write(tested_repo, TURNAROUND, TABLE_YAML)
    problems = rendered(tested_repo)
    assert any(p.startswith(f"{TEST_FILE}: ") and "delete it" in p for p in problems)


def test_a_hand_written_test_is_not_an_orphan(tested_repo: Path):
    write(tested_repo, f"{DP}/tests/my_own.sql", "select 1 where false\n")
    _remove_the_dbt_table(tested_repo)
    assert not any("my_own.sql" in p for p in rendered(tested_repo))


def test_generate_deletes_orphaned_generated_tests_and_stale_test_paths(tested_repo: Path):
    write(tested_repo, f"{DP}/tests/my_own.sql", "select 1 where false\n")
    _remove_the_dbt_table(tested_repo)
    result = generate_repo(tested_repo)
    assert result.report.ok
    assert not (tested_repo / TEST_FILE).exists()
    assert (tested_repo / DP / "tests/my_own.sql").exists()  # hand-written, so left alone
    assert TEST_FILE in {path.as_posix() for path in result.removed}
    project = (tested_repo / PROJECT).read_text()
    assert "model-paths" not in project
    assert "test-paths" not in project
    assert rendered(tested_repo) == []
