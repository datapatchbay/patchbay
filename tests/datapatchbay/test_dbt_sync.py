from pathlib import Path

import pytest
from plugin_fakes import FakeOrchestrator, register
from test_dbt import DP, MODEL, TABLE_YAML, rendered, write

from datapatchbay.generate import generate_repo

PROJECT = "dbt_project.yml"
PROPERTIES = f"{DP}/models/agg_lab_turnaround__turnaround.yml"
GROUP = f"{DP}/models/_group.yml"


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
