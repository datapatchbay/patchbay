"""`dbt parse` on the files that `dpb generate` writes, with the real dbt. Integration tests (ADR-0020).

The unit tests compare the generated dbt files with expected text. These tests ask dbt itself whether it accepts them,
so a change to the generated dbt files MUST pass `scripts/integration-tests` before it is pushed. dbt is installed from
the dependency group `dbt`, and a missing dbt fails the tests.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from dbt_helpers import DP, MODEL, PROFILES, TABLE, TABLE_YAML, dbt_parse, write
from plugin_fakes import FakeOrchestrator, register

from datapatchbay.dbt_manifest import check_dbt_reads
from datapatchbay.dbt_properties import generate_dbt_properties
from datapatchbay.generate import generate_repo
from datapatchbay.planning import plan_dataproducts
from datapatchbay.settings import load_settings
from datapatchbay.validation import load_and_validate

pytestmark = pytest.mark.dbt

PRODUCER = "dataproducts/sa_jaffle_orders"
ORDERS = f"{PRODUCER}/outputs/sa_jaffle_orders/orders.yaml"
PRODUCER_MODEL = f"{PRODUCER}/models/sa_jaffle_orders__orders.sql"
DBT_PROJECT = "name: jaffle_shop\nversion: '1.0.0'\nprofile: jaffle_shop\n"
NAME = "agg_order_turnaround__turnaround"
REF = f"{{{{ ref('{NAME}') }}}}"

TABLE_FILE = """\
schema_version: 1
name: turnaround
description: Days from order to result
columns:
  - name: order_id
    type: text
    description: The order
    rules: [not_null, unique]
  - name: status
    type: text
    rules:
      - rule: accepted_values
        values: [open, done]
        severity: warning
      - rule: not_null
        severity: none
  - name: customer_name
    type: text
    pii: true
  - name: days
    type: numeric(10, 2)
    rules:
      - rule: accepted_values
        values: [1, 2]
"""

ORDERS_FILE = """\
schema_version: 1
name: orders
description: One row per jaffle shop order
columns:
  - name: order_id
    type: text
    description: The order
    rules: [not_null, unique]
  - name: customer_id
    type: text
    pii: true
build:
  entrypoint: src/orders.py:build
  needs: [ingested_orders]
rules:
  - rule: row_count
    min: 1
"""


@pytest.fixture
def repo(jaffle_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The jaffle shop repo where `agg_order_turnaround` builds its table with dbt and reads `sa_jaffle_orders`."""
    # No orchestrator builds dbt tables into a DAG yet, so a fake one stands in.
    register(monkeypatch, "orchestrator", "fake", FakeOrchestrator)
    (jaffle_repo / "datapatchbay.yaml").write_text("schema_version: 1\norchestrator: fake\n")
    product = jaffle_repo / DP / "dataproduct.yaml"
    product.write_text(product.read_text() + "executor: dbt\n")
    write(jaffle_repo, TABLE, TABLE_YAML)
    write(jaffle_repo, MODEL, "select 1 as days\n")
    write(jaffle_repo, "dbt_project.yml", DBT_PROJECT)
    return jaffle_repo


def parse(repo: Path, tmp_path: Path) -> dict[str, Any]:
    """Run `dbt parse` on the repo with a profile that needs no server, and return the manifest it writes."""
    profiles = tmp_path / "profiles"
    write(profiles, "profiles.yml", PROFILES)
    dbt_parse(repo, profiles)
    return json.loads((repo / "target" / "manifest.json").read_text())


def test_dbt_parses_the_generated_properties(repo: Path, tmp_path: Path):
    write(repo, TABLE, TABLE_FILE)
    loaded, report = load_and_validate(repo)
    assert report.ok, [p.render() for p in report.problems]
    settings = load_settings(repo)
    for generated in generate_dbt_properties(plan_dataproducts(loaded, settings), settings):
        write(repo, str(generated.path), generated.content)
    write(repo, "dbt_project.yml", DBT_PROJECT + f"model-paths: ['{DP}/models']\n")
    manifest = parse(repo, tmp_path)
    model = manifest["nodes"]["model.jaffle_shop.agg_order_turnaround__turnaround"]
    assert model["config"]["contract"]["enforced"] is True
    assert model["group"] == "agg_order_turnaround"
    assert model["alias"] == "turnaround"
    assert model["schema"].endswith(model["config"]["schema"])
    tests = [n for n in manifest["nodes"].values() if n["resource_type"] == "test"]
    assert {t["config"]["severity"].lower() for t in tests} <= {"error", "warn"}
    assert {t["test_metadata"]["name"] for t in tests} == {"not_null", "unique", "accepted_values"}


def test_dbt_parses_a_model_that_reads_another_data_product(repo: Path, tmp_path: Path):
    write(repo, ORDERS, ORDERS_FILE)
    write(repo, MODEL, "select order_id as days from {{ source('sa_jaffle_orders', 'orders') }}\n")
    write(repo, TABLE, TABLE_YAML.replace("numeric", "text"))
    write(repo, "dbt_project.yml", DBT_PROJECT + f"model-paths: ['{DP}/models']\n")
    generate_repo(repo)
    manifest = parse(repo, tmp_path)
    model = manifest["nodes"]["model.jaffle_shop.agg_order_turnaround__turnaround"]
    assert model["sources"] == [["sa_jaffle_orders", "orders"]]
    source = manifest["sources"]["source.jaffle_shop.sa_jaffle_orders.orders"]
    assert source["schema"] == "sa_jaffle_orders"
    assert list(source["columns"]) == ["order_id", "customer_id"]


def test_dbt_parses_the_generated_tests(repo: Path, tmp_path: Path):
    write(
        repo,
        TABLE,
        TABLE_YAML + "rules:\n"
        "  - {rule: primary_key, columns: [days]}\n"
        "  - {rule: row_count, min: 1, severity: warning}\n"
        f"  - rule: sql\n    sql: select * from {REF} where days < 0;\n",
    )
    generate_repo(repo)
    manifest = parse(repo, tmp_path)
    tests = {n["name"]: n for n in manifest["nodes"].values() if n["resource_type"] == "test"}
    assert {name: test["config"]["severity"].lower() for name, test in tests.items()} == {
        f"{NAME}__primary_key": "error",
        f"{NAME}__row_count": "warn",
        f"{NAME}__sql": "error",
    }
    assert all(f"model.jaffle_shop.{NAME}" in test["depends_on"]["nodes"] for test in tests.values())


@pytest.fixture
def reader_repo(repo: Path) -> Path:
    """The repo for checking reads: the producer has a model too, and the reader has a hand-written source."""
    write(repo, PRODUCER_MODEL, "select 1 as order_id\n")
    write(
        repo,
        f"{DP}/models/extra_sources.yml",
        "sources:\n  - name: agg_weekly_orders\n    schema: agg_weekly_orders\n    tables:\n      - name: weekly\n",
    )
    generate_repo(repo)
    # `dpb generate` lists only the folders of data products built by dbt; the producer's model is a team's own choice.
    write(
        repo,
        "dbt_project.yml",
        DBT_PROJECT + f"model-paths: ['{DP}/models', '{PRODUCER}/models']\n",
    )
    return repo


def reads(repo: Path) -> list[str]:
    loaded, report = load_and_validate(repo)
    assert report.ok, [p.render() for p in report.problems]
    return [problem.render() for problem in check_dbt_reads(loaded, load_settings(repo))]


def test_dbt_parse_of_a_model_that_reads_only_its_input_port_passes_the_check(reader_repo: Path, tmp_path: Path):
    write(reader_repo, MODEL, "select 1 as days\nfrom {{ source('sa_jaffle_orders', 'orders') }}\n")
    parse(reader_repo, tmp_path)
    assert reads(reader_repo) == []


def test_dbt_parse_of_a_forbidden_ref_and_a_forbidden_source_is_reported_with_file_and_line(
    reader_repo: Path, tmp_path: Path
):
    write(
        reader_repo,
        MODEL,
        "select 1 as days\n"
        "from {{ ref('sa_jaffle_orders__orders') }}\n"
        "cross join {{ source('agg_weekly_orders', 'weekly') }}\n",
    )
    parse(reader_repo, tmp_path)
    ref_problem, source_problem = reads(reader_repo)
    assert ref_problem.startswith(f"{MODEL}:2: ")
    assert "'agg_order_turnaround__turnaround'" in ref_problem
    assert "'sa_jaffle_orders__orders'" in ref_problem
    assert source_problem.startswith(f"{MODEL}:3: ")
    assert "'agg_weekly_orders'" in source_problem
