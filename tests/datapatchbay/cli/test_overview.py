import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datapatchbay.cli import app

ORCHESTRATOR_HINT = "orchestrator can only be set in datapatchbay.yaml or dataproduct.yaml"
OUT_PORT = "dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/port.yaml"
IN_PORT = "dataproducts/sa_ilab_orders/inputs/sa_ilab_orders_private/port.yaml"
TABLE = "dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/orders.yaml"


@pytest.fixture
def in_repo(sample_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(sample_repo)
    return sample_repo


def test_list_prints_every_data_product(runner: CliRunner, in_repo: Path):
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0, result.output
    assert "agg_lab_turnaround" in result.stdout
    assert "sa_ilab_orders" in result.stdout
    assert "Joe Dev" in result.stdout


def test_list_json_matches_the_content(runner: CliRunner, in_repo: Path):
    result = runner.invoke(app, ["list", "--json"])
    data = json.loads(result.stdout)
    assert [entry["folder"] for entry in data] == ["agg_lab_turnaround", "sa_ilab_orders"]
    assert data[1]["technical_owner"] == "Joe Dev"


def test_describe_prints_settings_with_their_levels(runner: CliRunner, in_repo: Path):
    result = runner.invoke(app, ["describe", "sa_ilab_orders"])
    assert result.exit_code == 0, result.output
    assert "orchestrator: prefect  (dataproduct" in result.stdout
    assert "image: registry/orders:2  (table" in result.stdout
    assert "read by: agg_lab_turnaround" in result.stdout


def test_describe_json_has_the_same_content(runner: CliRunner, in_repo: Path):
    result = runner.invoke(app, ["describe", "sa_ilab_orders", "--json"])
    data = json.loads(result.stdout)
    assert data["outputs"][0]["read_by"] == ["agg_lab_turnaround"]
    assert data["outputs"][0]["tables"][0]["settings"]["image"]["level"] == "table"


def test_describe_unknown_name_names_the_data_products_that_exist(runner: CliRunner, in_repo: Path):
    result = runner.invoke(app, ["describe", "nope"])
    assert result.exit_code == 2
    assert "'nope'" in result.output
    assert "agg_lab_turnaround, sa_ilab_orders" in result.output


def test_list_warns_on_stderr_when_files_have_problems(runner: CliRunner, in_repo: Path):
    (in_repo / "dataproducts/agg_lab_turnaround/dataproduct.yaml").write_text("schema_version: 1\nbad: x\n")
    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0
    assert "problem(s) found" in result.stderr
    assert [e["folder"] for e in json.loads(result.stdout)] == ["sa_ilab_orders"]


@pytest.mark.parametrize("relative", [OUT_PORT, IN_PORT])
def test_validate_rejects_orchestrator_on_a_port(runner: CliRunner, in_repo: Path, relative: str):
    path = in_repo / relative
    path.write_text(path.read_text().replace("kind: schema\n", "kind: schema\norchestrator: airflow\n", 1))
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1
    assert f"{relative}:3: {ORCHESTRATOR_HINT}" in result.stderr


def test_validate_rejects_orchestrator_in_a_table_build_block(runner: CliRunner, in_repo: Path):
    path = in_repo / TABLE
    path.write_text(path.read_text().replace("build:\n", "build:\n  orchestrator: airflow\n"))
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1
    assert f"{TABLE}:" in result.stderr
    assert ORCHESTRATOR_HINT in result.stderr


def test_validate_accepts_orchestrator_at_root_and_data_product(runner: CliRunner, in_repo: Path):
    (in_repo / "datapatchbay.yaml").write_text("schema_version: 1\norchestrator: airflow\n")
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.stderr


def test_validate_accepts_cascading_settings_at_every_level(runner: CliRunner, in_repo: Path):
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.stderr
