import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datapatchbay import schemas
from datapatchbay.cli import app


@pytest.mark.parametrize("kind", schemas.KINDS)
def test_schema_prints_the_json_schema_of_a_kind(runner: CliRunner, kind: str):
    result = runner.invoke(app, ["schema", kind])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == schemas.json_schema(kind)


def test_schema_without_a_kind_prints_all_four_by_kind(runner: CliRunner):
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {kind: schemas.json_schema(kind) for kind in schemas.KINDS}


def test_schema_rejects_an_unknown_kind(runner: CliRunner):
    result = runner.invoke(app, ["schema", "nope"])
    assert result.exit_code == 2


def test_schema_works_outside_a_repo(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["schema", "root"]).exit_code == 0
