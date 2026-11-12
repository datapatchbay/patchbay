import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datapatchbay.cli import app

VALID_DATAPRODUCT = """\
schema_version: 1
name: ilab_orders
kind: source-aligned
owner: Jane Doe
"""

Writer = Callable[[str, str], Path]


def test_validate_exits_zero_on_valid_repo(runner: CliRunner, repo: Path, write_dataproduct: Writer):
    write_dataproduct("sa_ilab_orders", VALID_DATAPRODUCT)
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.output


def test_validate_accepts_repo_without_dataproducts(runner: CliRunner, repo: Path):
    assert runner.invoke(app, ["validate"]).exit_code == 0


def test_validate_fails_outside_repo(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["validate"])
    assert result.exit_code != 0
    assert "no datapatchbay.yaml found" in result.output


def test_validate_finds_repo_root_from_subdirectory(
    runner: CliRunner, repo: Path, write_dataproduct: Writer, monkeypatch: pytest.MonkeyPatch
):
    write_dataproduct("sa_ilab_orders", VALID_DATAPRODUCT + "ownr: x\n")
    monkeypatch.chdir(repo / "dataproducts")
    result = runner.invoke(app, ["validate"])
    assert result.exit_code != 0
    assert "dataproducts/sa_ilab_orders/dataproduct.yaml:5: unknown key 'ownr'" in result.output


def test_validate_reports_unknown_key_with_file_and_line(runner: CliRunner, repo: Path, write_dataproduct: Writer):
    write_dataproduct("sa_ilab_orders", VALID_DATAPRODUCT + "ownr: x\n")
    result = runner.invoke(app, ["validate"])
    assert result.exit_code != 0
    assert "dataproducts/sa_ilab_orders/dataproduct.yaml:5: unknown key 'ownr'" in result.output


def test_validate_reports_all_problems_across_files_in_one_run(
    runner: CliRunner, repo: Path, write_dataproduct: Writer
):
    (repo / "datapatchbay.yaml").write_text("schema_version: 1\nwharehouse: x\n")
    write_dataproduct("a", "schema_version: 1\nname: a\nkind: k\nowner: o\nfoo: 1\nbar: 2\n")
    write_dataproduct("b", "schema_version: 1\nname: b\nkind: k\n")
    result = runner.invoke(app, ["validate", "--json"])
    problems = json.loads(result.stdout)["problems"]
    found = {(p["file"], p["line"]) for p in problems}
    assert found == {
        ("datapatchbay.yaml", 2),
        ("dataproducts/a/dataproduct.yaml", 5),
        ("dataproducts/a/dataproduct.yaml", 6),
        ("dataproducts/b/dataproduct.yaml", 1),
    }


def test_validate_accepts_meta_map_with_any_content(runner: CliRunner, repo: Path, write_dataproduct: Writer):
    write_dataproduct("a", VALID_DATAPRODUCT + "meta:\n  team: {slack: '#lab', tags: [a, b]}\n  n: 3\n")
    (repo / "datapatchbay.yaml").write_text("schema_version: 1\nmeta: {anything: [1, 2]}\n")
    assert runner.invoke(app, ["validate"]).exit_code == 0


def test_validate_reports_missing_schema_version(runner: CliRunner, repo: Path, write_dataproduct: Writer):
    write_dataproduct("a", "name: a\nkind: k\nowner: o\n")
    result = runner.invoke(app, ["validate"])
    assert result.exit_code != 0
    assert "dataproducts/a/dataproduct.yaml:1: missing schema_version" in result.output


def test_validate_reports_schema_version_newer_than_known(runner: CliRunner, repo: Path, write_dataproduct: Writer):
    write_dataproduct("a", "schema_version: 2\nname: a\nbrand_new_key: 1\n")
    result = runner.invoke(app, ["validate", "--json"])
    problems = json.loads(result.stdout)["problems"]
    assert len(problems) == 1
    assert problems[0]["line"] == 1
    assert "schema_version 2 is newer" in problems[0]["message"]


def test_validate_reports_invalid_yaml_with_line(runner: CliRunner, repo: Path, write_dataproduct: Writer):
    write_dataproduct("a", "schema_version: 1\nname: [unclosed\n")
    result = runner.invoke(app, ["validate", "--json"])
    problem = json.loads(result.stdout)["problems"][0]
    assert problem["file"] == "dataproducts/a/dataproduct.yaml"
    assert problem["line"] is not None
    assert problem["message"].startswith("invalid YAML")


def test_validate_reports_empty_file(runner: CliRunner, repo: Path, write_dataproduct: Writer):
    write_dataproduct("a", "")
    assert runner.invoke(app, ["validate"]).exit_code != 0


def test_validate_reports_wrong_type_with_line_of_list_item(runner: CliRunner, repo: Path, write_dataproduct: Writer):
    write_dataproduct("a", VALID_DATAPRODUCT + "inputs:\n  - ok\n  - [nested]\n")
    problem = json.loads(runner.invoke(app, ["validate", "--json"]).stdout)["problems"][0]
    assert problem["line"] == 7


def test_validate_json_on_valid_repo(runner: CliRunner, repo: Path, write_dataproduct: Writer):
    write_dataproduct("a", VALID_DATAPRODUCT)
    result = runner.invoke(app, ["validate", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"ok": True, "dataproducts_checked": 1, "problems": []}


def test_validate_json_has_only_json_on_stdout_and_nonzero_exit_on_problems(
    runner: CliRunner, repo: Path, write_dataproduct: Writer
):
    write_dataproduct("a", VALID_DATAPRODUCT + "x: 1\n")
    result = runner.invoke(app, ["validate", "--json"])
    assert result.exit_code != 0
    assert json.loads(result.stdout)["ok"] is False
