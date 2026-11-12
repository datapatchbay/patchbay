"""The example repo in `examples/jaffle_shop`: a Python data product and a dbt data product that reads its output port.

These tests need neither dbt nor Airflow nor a warehouse (ADR-0020). They validate a copy of the example with a
hand-written dbt manifest. The tests marked `dbt` run the real `dbt parse` on a copy, and the end-to-end run in
Airflow against a real Postgres is `tests/airflow/run_example.py`, an integration test.
"""

import filecmp
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datapatchbay.cli import app

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "jaffle_shop"
READER = "dataproducts/agg_order_turnaround"
MODEL = f"{READER}/models/agg_order_turnaround__turnaround.sql"
MANIFEST = "target/manifest.json"
PROJECT = "jaffle_shop"
EMPTY_MANIFEST = {"metadata": {"project_name": PROJECT}, "nodes": {}, "sources": {}}


@pytest.fixture
def in_example(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A copy of the example with an empty dbt manifest, which is all that `dpb validate` needs from dbt here."""
    copy = tmp_path / "jaffle_shop"
    shutil.copytree(EXAMPLE, copy, ignore=shutil.ignore_patterns("target", "logs"))
    (copy / MANIFEST).parent.mkdir(exist_ok=True)
    (copy / MANIFEST).write_text(json.dumps(EMPTY_MANIFEST))
    monkeypatch.chdir(copy)
    return copy


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_the_example_passes_validate(runner: CliRunner, in_example: Path):
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.output
    assert "ok: 2 data product(s) valid" in result.stdout


def test_the_example_has_a_python_data_product_and_a_dbt_data_product_that_reads_it(
    runner: CliRunner, in_example: Path
):
    listing = runner.invoke(app, ["list"])
    assert listing.exit_code == 0, listing.output
    assert "source-aligned" in listing.stdout
    assert "aggregate" in listing.stdout
    orders = runner.invoke(app, ["describe", "sa_jaffle_orders"])
    assert orders.exit_code == 0, orders.output
    assert "customer_id" in orders.stdout
    assert "pii" in orders.stdout
    assert "executor: python" in orders.stdout
    turnaround = runner.invoke(app, ["describe", "agg_order_turnaround"])
    assert turnaround.exit_code == 0, turnaround.output
    assert "sa_jaffle_orders" in turnaround.stdout
    assert "executor: dbt" in turnaround.stdout


def test_the_dbt_model_reads_the_output_port_through_the_generated_source(in_example: Path):
    assert "source('sa_jaffle_orders', 'orders')" in (in_example / MODEL).read_text()
    sources = (in_example / f"{READER}/models/_sources.yml").read_text()
    assert "name: sa_jaffle_orders" in sources


def test_generate_writes_one_dag_file_per_data_product(runner: CliRunner, in_example: Path, tmp_path: Path):
    result = runner.invoke(app, ["generate", "--output", str(tmp_path / "dags")])
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in (tmp_path / "dags").iterdir()) == ["agg_order_turnaround.py", "sa_jaffle_orders.py"]
    dag = (tmp_path / "dags" / "agg_order_turnaround.py").read_text()
    assert 'build_dbt = _command_task("build_dbt"' in dag


def test_the_generated_dbt_files_are_committed_and_up_to_date(runner: CliRunner, in_example: Path, tmp_path: Path):
    before = tmp_path / "before"
    shutil.copytree(in_example, before)
    result = runner.invoke(app, ["generate", "--output", str(tmp_path / "dags")])
    assert result.exit_code == 0, result.output
    for relative in (f"{READER}/models", f"{READER}/tests"):
        comparison = filecmp.dircmp(before / relative, in_example / relative)
        assert (comparison.left_only, comparison.right_only, comparison.diff_files) == ([], [], []), relative
    assert filecmp.cmp(before / "dbt_project.yml", in_example / "dbt_project.yml", shallow=False)


def test_a_model_that_reads_a_private_schema_of_the_python_data_product_fails_validate(
    runner: CliRunner, in_example: Path
):
    source = {
        "resource_type": "source",
        "source_name": "sa_jaffle_orders_private",
        "name": "orders",
        "package_name": PROJECT,
        "schema": "sa_jaffle_orders_private",
    }
    model = {
        "resource_type": "model",
        "name": "agg_order_turnaround__turnaround",
        "package_name": PROJECT,
        "original_file_path": MODEL,
        "depends_on": {"nodes": ["source.jaffle_shop.sa_jaffle_orders_private.orders"]},
    }
    manifest = {
        **EMPTY_MANIFEST,
        "nodes": {"model.jaffle_shop.agg_order_turnaround__turnaround": model},
        "sources": {"source.jaffle_shop.sa_jaffle_orders_private.orders": source},
    }
    (in_example / MANIFEST).write_text(json.dumps(manifest))
    result = runner.invoke(app, ["validate"])
    assert result.exit_code != 0
    assert "private schema 'sa_jaffle_orders_private'" in result.output
