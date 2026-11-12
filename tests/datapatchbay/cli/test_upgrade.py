from pathlib import Path

import pytest
from ruamel.yaml.comments import CommentedMap
from typer.testing import CliRunner

from datapatchbay import upgrade
from datapatchbay.cli import app


def rename_owner(data: CommentedMap) -> None:
    if "ownr" in data:
        upgrade.rename_key(data, "ownr", "owner")


@pytest.fixture
def outdated(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo one version behind, with a test-only migration registered."""
    monkeypatch.setattr(upgrade, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(upgrade, "MIGRATIONS", {1: upgrade.Migration(rename_owner)})
    path = repo / "dataproducts" / "a" / "dataproduct.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("schema_version: 1\nownr: Jane  # who\n")
    return path


def test_upgrade_says_nothing_to_do_and_exits_zero(runner: CliRunner, repo: Path):
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 0, result.output
    assert "nothing to do" in result.output


def test_upgrade_rewrites_files_and_lists_them(runner: CliRunner, outdated: Path):
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 0, result.output
    assert "upgraded dataproducts/a/dataproduct.yaml (1 -> 2)" in result.output
    assert outdated.read_text() == "schema_version: 2\nowner: Jane  # who\n"


def test_upgrade_dry_run_shows_a_diff_and_writes_nothing(runner: CliRunner, outdated: Path):
    result = runner.invoke(app, ["upgrade", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "would upgrade dataproducts/a/dataproduct.yaml (1 -> 2)" in result.output
    assert "-ownr: Jane  # who" in result.output
    assert "+owner: Jane  # who" in result.output
    assert outdated.read_text() == "schema_version: 1\nownr: Jane  # who\n"


def test_upgrade_refuses_newer_file_with_exit_one(runner: CliRunner, repo: Path):
    (repo / "datapatchbay.yaml").write_text("schema_version: 7\n")
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 1
    assert "datapatchbay.yaml:1: schema_version 7 is newer than this datapatchbay understands" in result.output
    assert (repo / "datapatchbay.yaml").read_text() == "schema_version: 7\n"
