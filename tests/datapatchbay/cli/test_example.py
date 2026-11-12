"""The example repo in `examples/lab`: two data products that stand in for a first deployment.

The end-to-end run against a real Postgres and Airflow is the CI job `example` (`tests/airflow/run_example.py`).
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from datapatchbay.cli import app

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "lab"


@pytest.fixture
def in_example(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(EXAMPLE)
    return EXAMPLE


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_the_example_passes_validate(runner: CliRunner, in_example: Path):
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.output
    assert "ok: 2 data product(s) valid" in result.stdout


def test_the_example_has_a_source_aligned_and_an_aggregate_data_product(runner: CliRunner, in_example: Path):
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0, result.output
    assert "source-aligned" in result.stdout
    assert "aggregate" in result.stdout


def test_the_source_aligned_data_product_has_a_pii_column_and_the_aggregate_reads_its_output_port(
    runner: CliRunner, in_example: Path
):
    orders = runner.invoke(app, ["describe", "sa_ilab_orders"])
    assert orders.exit_code == 0, orders.output
    assert "patient_id" in orders.stdout
    assert "pii" in orders.stdout
    turnaround = runner.invoke(app, ["describe", "agg_lab_turnaround"])
    assert turnaround.exit_code == 0, turnaround.output
    assert "sa_ilab_orders" in turnaround.stdout


def test_generate_writes_one_dag_file_per_data_product(runner: CliRunner, in_example: Path, tmp_path: Path):
    result = runner.invoke(app, ["generate", "--output", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in tmp_path.iterdir()) == ["agg_lab_turnaround.py", "sa_ilab_orders.py"]
