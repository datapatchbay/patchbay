import json
from pathlib import Path

from typer.testing import CliRunner

from datapatchbay.cli import app


def test_config_prints_each_setting_with_value_and_origin(runner: CliRunner, repo: Path):
    (repo / "datapatchbay.yaml").write_text("schema_version: 1\nruntime: docker\n")
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0, result.output
    lines = {line.split()[0]: line for line in result.stdout.splitlines()}
    assert lines["runtime"].split() == ["runtime", "docker", "(datapatchbay.yaml)"]
    assert lines["warehouse"].split() == ["warehouse", "postgres", "(defaults)"]
    assert lines["conventions.domains"].split() == ["conventions.domains", "[]", "(defaults)"]
    assert "conventions.kinds.aggregate.prefix" in lines


def test_config_json_prints_the_same_as_json(runner: CliRunner, repo: Path):
    (repo / "datapatchbay.yaml").write_text("schema_version: 1\nruntime: docker\n")
    result = runner.invoke(app, ["config", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["runtime"] == {"value": "docker", "origin": "datapatchbay.yaml"}
    assert data["warehouse"] == {"value": "postgres", "origin": "defaults"}
    assert data["conventions.domains"] == {"value": [], "origin": "defaults"}


def test_config_fails_on_invalid_file_with_line(runner: CliRunner, repo: Path):
    (repo / "datapatchbay.yaml").write_text("schema_version: 1\nseverity: loud\n")
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 2
    assert "datapatchbay.yaml:2" in result.output
