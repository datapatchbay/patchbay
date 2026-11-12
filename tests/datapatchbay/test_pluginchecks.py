from pathlib import Path

import pytest
from plugin_fakes import FakeOrchestrator, register

from datapatchbay.validation import validate_repo

ORDERS = "dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/orders.yaml"
INGESTED = "dataproducts/sa_ilab_orders/inputs/sa_ilab_orders_private/ingested.yaml"


def rendered(repo: Path) -> list[str]:
    return [problem.render() for problem in validate_repo(repo).problems]


def test_a_repo_that_uses_only_installed_plugins_is_valid(lab_repo: Path):
    assert rendered(lab_repo) == []


def test_a_runtime_without_a_plugin_names_the_data_product_table_and_line(lab_repo: Path):
    path = lab_repo / ORDERS
    path.write_text(path.read_text().replace("build:\n", "build:\n  runtime: podman\n"))
    assert rendered(lab_repo) == [
        f"{ORDERS}:7: runtime 'podman' has no plugin (data product 'sa_ilab_orders', table 'orders'); "
        "available runtime plugins: docker, kubernetes, worker"
    ]


def test_an_executor_without_a_plugin_is_reported_where_it_is_set_for_each_table_it_applies_to(lab_repo: Path):
    port = lab_repo / "dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/port.yaml"
    port.write_text(port.read_text() + "executor: spark\n")
    assert rendered(lab_repo) == [
        "dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/port.yaml:8: executor 'spark' has no plugin "
        "(data product 'sa_ilab_orders', table 'orders'); available executor plugins: dbt, python"
    ]


def test_a_root_level_runtime_is_reported_once_per_table_at_the_root_file(lab_repo: Path):
    (lab_repo / "datapatchbay.yaml").write_text("schema_version: 1\nruntime: podman\n")
    messages = rendered(lab_repo)
    assert len(messages) == 4
    assert messages[0].startswith("datapatchbay.yaml:2: runtime 'podman' has no plugin (data product ")
    assert any("table 'turnaround'" in message for message in messages)


def test_an_orchestrator_without_a_plugin_names_the_data_product(lab_repo: Path):
    product = lab_repo / "dataproducts/agg_lab_turnaround/dataproduct.yaml"
    product.write_text(product.read_text() + "orchestrator: prefect\n")
    assert rendered(lab_repo) == [
        "dataproducts/agg_lab_turnaround/dataproduct.yaml:7: orchestrator 'prefect' has no plugin "
        "(data product 'agg_lab_turnaround'); available orchestrator plugins: airflow"
    ]


def test_a_warehouse_without_a_plugin_is_reported_at_the_root_file(lab_repo: Path):
    (lab_repo / "datapatchbay.yaml").write_text("schema_version: 1\nwarehouse: snowflake\n")
    assert rendered(lab_repo) == [
        "datapatchbay.yaml:2: warehouse 'snowflake' has no plugin (the repo); "
        "available warehouse plugins: duckdb, postgres"
    ]


def test_a_plugin_installed_later_makes_its_name_valid(lab_repo: Path, monkeypatch: pytest.MonkeyPatch):
    register(monkeypatch, "orchestrator", "prefect", FakeOrchestrator)
    product = lab_repo / "dataproducts/agg_lab_turnaround/dataproduct.yaml"
    product.write_text(product.read_text() + "orchestrator: prefect\n")
    assert rendered(lab_repo) == []


def test_the_plugin_check_is_skipped_when_the_root_file_is_invalid(lab_repo: Path):
    (lab_repo / "datapatchbay.yaml").write_text("schema_version: 1\nwharehouse: x\n")
    assert [problem.message.split(";")[0] for problem in validate_repo(lab_repo).problems] == [
        "unknown key 'wharehouse'"
    ]


def test_validate_fails_a_container_runtime_without_an_image(lab_repo: Path):
    path = lab_repo / INGESTED
    path.write_text(path.read_text().replace("build:\n", "build:\n  runtime: docker\n"))
    assert rendered(lab_repo) == [
        f"{INGESTED}:7: runtime 'docker' needs an image, but none is set "
        "(data product 'sa_ilab_orders', table 'ingested_orders'); set `image` at the root, data product, port or table"
    ]


def test_validate_accepts_an_image_set_at_any_level(lab_repo: Path):
    port = lab_repo / "dataproducts/sa_ilab_orders/inputs/sa_ilab_orders_private/port.yaml"
    port.write_text(port.read_text() + "image: lab:1\n")
    path = lab_repo / INGESTED
    path.write_text(path.read_text().replace("build:\n", "build:\n  runtime: docker\n"))
    assert rendered(lab_repo) == []


DBT_TABLE = "dataproducts/agg_lab_weekly/outputs/agg_lab_weekly/weekly_summary.yaml"
PYTHON_TABLE = "dataproducts/agg_lab_weekly/outputs/agg_lab_weekly/weekly.yaml"


def test_validate_fails_a_dbt_table_on_a_runtime_that_cannot_run_dbt(lab_dbt_repo: Path):
    path = lab_dbt_repo / DBT_TABLE
    path.write_text(path.read_text().replace("build:\n", "build:\n  runtime: docker\n  image: lab:1\n"))
    assert rendered(lab_dbt_repo) == [
        f"{DBT_TABLE}:9: runtime 'docker' cannot run dbt (data product 'agg_lab_weekly', table 'weekly_summary'); "
        "set `runtime: worker` for the tables built by dbt"
    ]


def test_validate_fails_a_table_that_needs_a_dbt_table(lab_dbt_repo: Path):
    path = lab_dbt_repo / PYTHON_TABLE
    path.write_text(path.read_text().replace("needs: [", "needs: [weekly_summary, "))
    problems = rendered(lab_dbt_repo)
    assert len(problems) == 1
    assert problems[0].startswith(f"{PYTHON_TABLE}:")
    assert "table 'weekly' needs table 'weekly_summary', which dbt builds after the Python tables" in problems[0]
