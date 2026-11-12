from pathlib import Path

import pytest
from typer.testing import CliRunner

from datapatchbay.cli import app


@pytest.fixture
def in_lab_repo(lab_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(lab_repo)
    return lab_repo


def test_generate_writes_the_dag_files_and_lists_them(runner: CliRunner, in_lab_repo: Path):
    result = runner.invoke(app, ["generate"])
    assert result.exit_code == 0, result.output
    assert f"wrote {in_lab_repo.resolve() / 'generated' / 'sa_ilab_orders.py'}" in result.stdout
    assert "ok: 3 file(s) written" in result.stdout
    assert (in_lab_repo / "generated/sa_ilab_orders.py").is_file()


def test_generate_output_flag_overrides_the_folder_relative_to_the_working_directory(
    runner: CliRunner, in_lab_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(in_lab_repo / "dataproducts")
    result = runner.invoke(app, ["generate", "--output", "out"])
    assert result.exit_code == 0, result.output
    assert (in_lab_repo / "dataproducts/out/agg_lab_turnaround.py").is_file()
    assert not (in_lab_repo / "generated").exists()


def test_generate_validates_first_and_writes_nothing_when_the_repo_is_invalid(runner: CliRunner, in_lab_repo: Path):
    (in_lab_repo / "dataproducts/sa_ilab_orders/dataproduct.yaml").write_text("schema_version: 1\nnam: x\n")
    result = runner.invoke(app, ["generate"])
    assert result.exit_code == 1
    assert "dataproducts/sa_ilab_orders/dataproduct.yaml:2: unknown key 'nam'" in result.stderr
    assert "nothing was written" in result.stderr
    assert not (in_lab_repo / "generated").exists()


def test_generate_fails_for_a_runtime_without_a_plugin_and_names_data_product_and_table(
    runner: CliRunner, in_lab_repo: Path
):
    (in_lab_repo / "datapatchbay.yaml").write_text("schema_version: 1\nruntime: podman\n")
    result = runner.invoke(app, ["generate"])
    assert result.exit_code == 1
    assert "runtime 'podman' has no plugin (data product 'sa_ilab_orders', table 'orders')" in result.stderr
    assert not (in_lab_repo / "generated").exists()


def test_generate_reports_a_generation_failure_as_a_message_with_exit_code_two(runner: CliRunner, in_lab_repo: Path):
    table = in_lab_repo / "dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/orders.yaml"
    table.write_text(table.read_text().replace("  needs:", "  params:\n    since: 2025-01-01\n  needs:"))
    result = runner.invoke(app, ["generate"])
    assert result.exit_code == 2
    assert result.stderr.startswith("error: data product 'sa_ilab_orders': table 'orders':")
    assert "Traceback" not in result.output
