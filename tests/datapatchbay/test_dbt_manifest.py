import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from dbt_helpers import DP, MODEL, TABLE, TABLE_YAML, write
from plugin_fakes import FakeOrchestrator, register

from datapatchbay.dbt_manifest import check_dbt_reads
from datapatchbay.settings import load_settings
from datapatchbay.validation import load_and_validate, validate_repo

MANIFEST = "target/manifest.json"
PRODUCER = "dataproducts/sa_jaffle_orders"
READER_MODEL_ID = "model.jaffle_shop.agg_order_turnaround__turnaround"
PRODUCER_MODEL_ID = "model.jaffle_shop.sa_jaffle_orders__orders"
PRODUCER_MODEL = f"{PRODUCER}/models/sa_jaffle_orders__orders.sql"
SOURCE_ID = "source.jaffle_shop.sa_jaffle_orders.orders"


@pytest.fixture
def repo(jaffle_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The jaffle shop repo where `agg_order_turnaround` builds its table with dbt and reads `sa_jaffle_orders`."""
    register(monkeypatch, "orchestrator", "fake", FakeOrchestrator)
    (jaffle_repo / "datapatchbay.yaml").write_text("schema_version: 1\norchestrator: fake\n")
    product = jaffle_repo / DP / "dataproduct.yaml"
    product.write_text(product.read_text() + "executor: dbt\n")
    write(jaffle_repo, TABLE, TABLE_YAML)
    write(jaffle_repo, MODEL, "select 1 as days\n")
    write(jaffle_repo, "dbt_project.yml", "name: jaffle_shop\nversion: '1.0.0'\nprofile: jaffle_shop\n")
    return jaffle_repo


def reader_node(depends_on: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "resource_type": "model",
        "name": "agg_order_turnaround__turnaround",
        "package_name": "jaffle_shop",
        "unique_id": READER_MODEL_ID,
        "original_file_path": MODEL,
        "depends_on": {"macros": [], "nodes": depends_on},
        **extra,
    }


def source_node(source_name: str, name: str, schema: str | None = None) -> dict[str, Any]:
    return {
        "resource_type": "source",
        "source_name": source_name,
        "name": name,
        "package_name": "jaffle_shop",
        "schema": schema or source_name,
        "unique_id": f"source.jaffle_shop.{source_name}.{name}",
    }


def producer_node() -> dict[str, Any]:
    return {
        "resource_type": "model",
        "name": "sa_jaffle_orders__orders",
        "package_name": "jaffle_shop",
        "unique_id": PRODUCER_MODEL_ID,
        "original_file_path": PRODUCER_MODEL,
        "depends_on": {"nodes": []},
    }


def write_manifest(
    repo: Path, nodes: Sequence[dict[str, Any]], sources: Sequence[dict[str, Any]] = (), path: str = MANIFEST
) -> None:
    document = {
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json",
            "project_name": "jaffle_shop",
        },
        "nodes": {node["unique_id"]: node for node in nodes},
        "sources": {source["unique_id"]: source for source in sources},
        "something_new": {"dbt": "adds fields"},
    }
    write(repo, path, json.dumps(document))


def reads(repo: Path) -> list[str]:
    loaded, _, report = load_and_validate(repo)
    assert report.ok, [p.render() for p in report.problems]
    return [problem.render() for problem in check_dbt_reads(loaded, load_settings(repo))]


def test_a_missing_manifest_fails_and_says_to_run_dbt_parse(repo: Path):
    [problem] = reads(repo)
    assert problem.startswith(f"{MANIFEST}: ")
    assert "dbt parse" in problem


def test_a_repo_without_tables_built_by_dbt_needs_no_manifest(jaffle_repo: Path):
    assert reads(jaffle_repo) == []


def test_validate_reports_a_missing_manifest(repo: Path):
    assert any("dbt parse" in problem.message for problem in validate_repo(repo).problems)


def test_a_manifest_that_is_not_json_fails(repo: Path):
    write(repo, MANIFEST, "{not json")
    [problem] = reads(repo)
    assert problem.startswith(f"{MANIFEST}: ")
    assert "dbt parse" in problem


def test_a_manifest_without_nodes_fails(repo: Path):
    write(repo, MANIFEST, '{"metadata": {}}')
    [problem] = reads(repo)
    assert problem.startswith(f"{MANIFEST}: ")
    assert "nodes" in problem


def test_a_model_that_reads_the_source_of_its_input_port_passes(repo: Path):
    write_manifest(repo, [reader_node([SOURCE_ID])], [source_node("sa_jaffle_orders", "orders")])
    assert reads(repo) == []


def test_a_model_that_reads_a_model_of_its_own_data_product_passes(repo: Path):
    own = {**producer_node(), "original_file_path": f"{DP}/models/other.sql", "name": "other"}
    write_manifest(repo, [reader_node([PRODUCER_MODEL_ID]), own])
    assert reads(repo) == []


def test_a_ref_into_another_data_product_is_a_read_of_its_private_schema(repo: Path):
    write(repo, MODEL, "select 1\nfrom {{ ref('sa_jaffle_orders__orders') }}\n")
    write_manifest(repo, [reader_node([PRODUCER_MODEL_ID]), producer_node()])
    [problem] = reads(repo)
    assert problem.startswith(f"{MODEL}:2: ")
    assert "'agg_order_turnaround__turnaround'" in problem
    assert "'sa_jaffle_orders__orders'" in problem
    assert "'sa_jaffle_orders'" in problem
    assert "private" in problem


def test_a_read_without_a_findable_line_still_names_the_file(repo: Path):
    write(repo, MODEL, "select 1\n")
    write_manifest(repo, [reader_node([PRODUCER_MODEL_ID]), producer_node()])
    [problem] = reads(repo)
    assert problem.startswith(f"{MODEL}: ")


def test_a_source_of_an_output_port_without_an_input_port_fails_naming_the_port(repo: Path):
    write(repo, MODEL, "select 1\nfrom {{ source('agg_weekly_orders', 'weekly') }}\n")
    write_manifest(
        repo,
        [reader_node(["source.jaffle_shop.agg_weekly_orders.weekly"])],
        [source_node("agg_weekly_orders", "weekly")],
    )
    [problem] = reads(repo)
    assert problem.startswith(f"{MODEL}:2: ")
    assert "'agg_weekly_orders'" in problem
    assert "input port" in problem


def test_a_source_on_the_private_schema_of_another_data_product_fails(repo: Path):
    write_manifest(
        repo,
        [reader_node(["source.jaffle_shop.raw.orders"])],
        [source_node("raw", "orders", schema="sa_jaffle_orders_private")],
    )
    [problem] = reads(repo)
    assert problem.startswith(f"{MODEL}: ")
    assert "private" in problem
    assert "'sa_jaffle_orders'" in problem


def test_a_source_that_is_no_output_port_is_not_a_cross_product_read(repo: Path):
    write_manifest(repo, [reader_node(["source.jaffle_shop.raw.orders"])], [source_node("raw", "orders")])
    assert reads(repo) == []


def test_every_offending_dependency_is_reported(repo: Path):
    write_manifest(
        repo,
        [reader_node([PRODUCER_MODEL_ID, "source.jaffle_shop.agg_weekly_orders.weekly"]), producer_node()],
        [source_node("agg_weekly_orders", "weekly")],
    )
    assert len(reads(repo)) == 2


def test_a_model_of_another_dbt_package_is_ignored(repo: Path):
    package_model = {**reader_node([PRODUCER_MODEL_ID]), "package_name": "dbt_utils"}
    write_manifest(repo, [package_model, producer_node()])
    assert reads(repo) == []


def test_the_manifest_path_is_a_setting(repo: Path):
    (repo / "datapatchbay.yaml").write_text(
        "schema_version: 1\norchestrator: fake\ndbt:\n  manifest: build/dbt/manifest.json\n"
    )
    [problem] = reads(repo)
    assert problem.startswith("build/dbt/manifest.json: ")
    write_manifest(repo, [reader_node([])], path="build/dbt/manifest.json")
    assert reads(repo) == []


def test_validate_reports_a_forbidden_ref_after_the_other_checks_pass(repo: Path):
    write_manifest(repo, [reader_node([PRODUCER_MODEL_ID]), producer_node()])
    messages = [problem.message for problem in validate_repo(repo).problems]
    assert any("private" in message for message in messages)
