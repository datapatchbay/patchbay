"""`dpb validate` on a repo whose orchestrator is `local`: runtimes that cannot run there are refused (ADR-0022)."""

import json
from pathlib import Path

import pytest
from local_support import write_repo
from typer.testing import CliRunner

from datapatchbay.cli import app


@pytest.mark.parametrize("runtime", ["docker", "kubernetes"])
def test_validate_refuses_a_container_runtime_and_names_the_runtime_and_the_orchestrator(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runtime: str
):
    settings = (
        f"schema_version: 1\norchestrator: local\nwarehouse: duckdb\nruntime: {runtime}\nimage: registry/shop:1\n"
    )
    write_repo(tmp_path, **{"datapatchbay.yaml": settings})
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["validate", "--json"])

    assert result.exit_code == 1, result.output
    messages = [problem["message"] for problem in json.loads(result.stdout)["problems"]]
    assert messages
    for message in messages:
        assert f"the {runtime} runtime cannot render tasks for orchestrator 'local'" in message
    assert not (tmp_path / "generated").exists()
