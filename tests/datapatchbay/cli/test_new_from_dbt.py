import json
import shutil
from pathlib import Path

from dbt_helpers import write
from typer.testing import CliRunner

from datapatchbay.cli import app
from datapatchbay.files.yamlio import load_mapping
from datapatchbay.pipeline.generate import generate_repo
from datapatchbay.pipeline.validation import validate_repo

FLAGS = ["new", "--name", "orders", "--kind", "source-aligned", "--owner", "Jane Doe", "--no-input"]
FOLDER = "dataproducts/sa_orders"

PROPERTIES = """\
version: 2
models:
  - name: stg_orders
    description: One row per order.
    columns:
      - name: id
        data_type: bigint
        description: The order.
        tests:
          - unique
          - not_null:
              config:
                severity: warn
      - name: status
        data_type: text
        data_tests:
          - accepted_values:
              arguments:
                values: [placed, shipped]
          - relationships:
              arguments: {to: ref('customers'), field: id}
      - name: email
        data_type: text
        config:
          meta:
            pii: true
  - name: order_totals
    description: Totals.
    columns:
      - name: id
        data_type: bigint
        data_tests:
          - accepted_values:
              values: [1, 2]
              quote: false
          - unique:
              where: "id > 1"
    data_tests:
      - dbt_utils.unique_combination_of_columns:
          arguments: {combination_of_columns: [id]}
"""


def dbt_project(root: Path) -> Path:
    write(root, "old/models/stg_orders.sql", "select 1 as id, 'x' as status, 'e' as email\n")
    write(root, "old/models/order_totals.sql", "select id from {{ ref('stg_orders') }}\n")
    write(root, "old/models/_models.yml", PROPERTIES)
    return root / "old/models"


def invoke(runner: CliRunner, repo: Path, *extra: str):
    return runner.invoke(app, [*FLAGS, "--from-dbt", str(dbt_project(repo)), *extra])


def test_import_writes_table_files_and_copies_models(runner: CliRunner, repo: Path):
    result = invoke(runner, repo)
    assert result.exit_code == 0, result.output
    folder = repo / FOLDER
    assert (folder / "outputs/sa_orders/stg_orders.yaml").read_text() == (
        "schema_version: 1\n"
        "name: stg_orders\n"
        "description: One row per order.\n"
        "columns:\n"
        "  - name: id\n"
        "    type: bigint\n"
        "    description: The order.\n"
        "    rules:\n"
        "      - unique\n"
        "      - rule: not_null\n"
        "        severity: warning\n"
        "  - name: status\n"
        "    type: text\n"
        "    rules:\n"
        "      - rule: accepted_values\n"
        "        values:\n"
        "          - placed\n"
        "          - shipped\n"
        "  - name: email\n"
        "    type: text\n"
        "    pii: true\n"
    )
    assert (
        "      - rule: accepted_values\n        values:\n          - 1\n          - 2\n"
        in (folder / "outputs/sa_orders/order_totals.yaml").read_text()
    )
    assert "executor: dbt" in (folder / "dataproduct.yaml").read_text()
    # copied, with ref() renamed to the dbt_model template; the original stays
    assert (folder / "models/sa_orders__order_totals.sql").read_text() == (
        "select id from {{ ref('sa_orders__stg_orders') }}\n"
    )
    assert (repo / "old/models/order_totals.sql").is_file()
    assert not (folder / "src").exists()
    assert "example" not in result.output


def test_unmapped_tests_are_reported_in_text_and_json(runner: CliRunner, repo: Path):
    result = invoke(runner, repo)
    assert "not imported: stg_orders.status relationships" in result.output
    assert "not imported: order_totals.id unique" in result.output  # `where` changes what the rule means
    assert "not imported: order_totals dbt_utils.unique_combination_of_columns" in result.output
    shutil.rmtree(repo / FOLDER)
    data = json.loads(invoke(runner, repo, "--json").stdout)
    tests = {(t["model"], t.get("column"), t["test"]) for t in data["unmapped_tests"]}
    assert ("stg_orders", "status", "relationships") in tests
    assert ("order_totals", None, "dbt_utils.unique_combination_of_columns") in tests
    assert all(t["reason"] for t in data["unmapped_tests"])
    assert any(p.endswith("stg_orders.yaml") for p in data["created"])


def prepare_dbt(repo: Path) -> None:
    (repo / "dbt_project.yml").write_text("name: lab\nversion: '1.0'\nprofile: lab\n")
    assert generate_repo(repo).report.ok
    write(repo, "target/manifest.json", '{"metadata": {}, "nodes": {}, "sources": {}}')


def test_imported_data_product_validates_after_generate(runner: CliRunner, repo: Path):
    assert invoke(runner, repo).exit_code == 0
    prepare_dbt(repo)
    assert (repo / "old/models/_models.yml").read_text() == PROPERTIES  # never deleted or edited
    assert [p.render() for p in validate_repo(repo).problems] == []


def test_hand_written_properties_in_the_new_models_folder_are_flagged_not_deleted(runner: CliRunner, repo: Path):
    assert invoke(runner, repo).exit_code == 0
    prepare_dbt(repo)
    hand = repo / FOLDER / "models/_hand.yml"
    hand.write_text("models:\n  - name: sa_orders__stg_orders\n")
    assert any("already declared" in p.render() for p in validate_repo(repo).problems)
    assert hand.is_file()


def test_missing_values_still_fail_with_no_input(runner: CliRunner, repo: Path):
    result = runner.invoke(app, ["new", "--no-input", "--from-dbt", str(dbt_project(repo))])
    assert result.exit_code == 2
    assert "--name, --kind, --owner" in result.output


def test_models_without_sql_or_properties_are_skipped_and_reported(runner: CliRunner, repo: Path):
    root = dbt_project(repo)
    write(repo, "old/models/lonely.sql", "select 1 as a\n")
    (root / "extra.yml").write_text("models:\n  - name: ghost\n    columns:\n      - name: a\n        data_type: int\n")
    data = json.loads(invoke(runner, repo, "--json").stdout)
    assert {s["model"] for s in data["skipped"]} == {"lonely", "ghost"}
    assert not (repo / FOLDER / "models/sa_orders__lonely.sql").exists()


def test_column_without_data_type_gets_text_and_is_reported(runner: CliRunner, repo: Path):
    write(repo, "old/models/stg_orders.sql", "select 1 as id\n")
    write(
        repo,
        "old/models/_models.yml",
        "models:\n  - name: stg_orders\n    columns:\n      - name: id\n        tests: [unique]\n",
    )
    result = runner.invoke(app, [*FLAGS, "--from-dbt", str(repo / "old/models")])
    assert result.exit_code == 0, result.output
    assert "type: text" in (repo / FOLDER / "outputs/sa_orders/stg_orders.yaml").read_text()
    assert "no data_type: stg_orders.id" in result.output


def test_from_dbt_conflicts_with_source_and_missing_path_fails(runner: CliRunner, repo: Path):
    result = invoke(runner, repo, "--source", "ilab")
    assert result.exit_code == 2
    assert "--source" in result.output
    result = runner.invoke(app, [*FLAGS, "--from-dbt", str(repo / "nope")])
    assert result.exit_code == 2
    assert "nope" in result.output
    assert not (repo / FOLDER).exists()


def test_non_snake_case_model_name_fails_and_writes_nothing(runner: CliRunner, repo: Path):
    root = dbt_project(repo)
    write(repo, "old/models/Bad-Name.sql", "select 1 as a\n")
    (root / "bad.yml").write_text(
        "models:\n  - name: Bad-Name\n    columns:\n      - name: a\n        data_type: int\n"
    )
    result = invoke(runner, repo)
    assert result.exit_code == 2
    assert "Bad-Name" in result.output
    assert not (repo / "dataproducts").exists()


def test_round_trip_generate_reproduces_the_imported_properties(runner: CliRunner, repo: Path):
    assert invoke(runner, repo).exit_code == 0
    prepare_dbt(repo)
    models = {
        m["name"]: m
        for file in (repo / FOLDER / "models").glob("sa_orders__*.yml")
        for m in load_mapping(file)["models"]
    }
    stg = models["sa_orders__stg_orders"]
    assert stg["description"] == "One row per order."
    columns = {c["name"]: c for c in stg["columns"]}
    assert {name: c["data_type"] for name, c in columns.items()} == {"id": "bigint", "status": "text", "email": "text"}
    assert columns["id"]["description"] == "The order."
    assert columns["id"]["data_tests"] == [
        {"unique": {"config": {"severity": "error"}}},
        {"not_null": {"config": {"severity": "warn"}}},
    ]
    assert columns["status"]["data_tests"] == [
        {"accepted_values": {"arguments": {"values": ["placed", "shipped"]}, "config": {"severity": "error"}}}
    ]
    assert "data_tests" not in columns["email"]
    totals = {c["name"]: c for c in models["sa_orders__order_totals"]["columns"]}
    assert totals["id"]["data_tests"] == [
        {"accepted_values": {"arguments": {"values": [1, 2], "quote": False}, "config": {"severity": "error"}}}
    ]


def test_refs_that_cannot_be_renamed_are_reported_and_left_as_written(runner: CliRunner, repo: Path):
    root = dbt_project(repo)
    write(
        repo,
        "old/models/order_totals.sql",
        'select * from {{ref( "stg_orders" )}}\n'
        "join {{ ref('pkg', 'stg_orders') }} using (id)\n"
        "join {{ ref('stg_orders', v=2) }} using (id)\n"
        "join {{ ref('customers') }} using (id)\n",
    )
    data = json.loads(runner.invoke(app, [*FLAGS, "--from-dbt", str(root), "--json"]).stdout)
    assert {(r["model"], r["call"]) for r in data["unrewritten_refs"]} == {
        ("order_totals", "ref('pkg', 'stg_orders')"),
        ("order_totals", "ref('stg_orders', v=2)"),
        ("order_totals", "ref('customers')"),
    }
    sql = (repo / FOLDER / "models/sa_orders__order_totals.sql").read_text()
    assert '{{ref( "sa_orders__stg_orders" )}}' in sql
    assert "ref('pkg', 'stg_orders')" in sql


def test_unreadable_properties_file_is_reported(runner: CliRunner, repo: Path):
    root = dbt_project(repo)
    (root / "broken.yml").write_text("models: [unclosed\n")
    data = json.loads(invoke(runner, repo, "--json").stdout)
    assert any(s["model"].endswith("broken.yml") for s in data["skipped"])
