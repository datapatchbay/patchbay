"""The validate pipeline: one gate that plans once, and the commands that consume the plans."""

import sys
from pathlib import Path

import pytest
from dbt_helpers import write

from datapatchbay import planning
from datapatchbay.generate import generate_repo
from datapatchbay.planning import PlannedRepo
from datapatchbay.problems import Report
from datapatchbay.validation import plan_repo, validate_repo

MANIFEST = '{"metadata": {}, "nodes": {}, "sources": {}}'


@pytest.fixture
def plan_calls(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Count the calls of `plan_dataproducts`, whichever module imported it."""
    calls: list[int] = []
    real = planning.plan_dataproducts

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    for module in list(sys.modules.values()):
        if getattr(module, "plan_dataproducts", None) is real:
            monkeypatch.setattr(module, "plan_dataproducts", counting)
    return calls


def test_the_gate_returns_the_plans_of_a_valid_repo(jaffle_repo: Path):
    planned = plan_repo(jaffle_repo)
    assert isinstance(planned, PlannedRepo)
    assert [plan.folder for plan in planned.plans] == ["agg_order_turnaround", "agg_weekly_orders", "sa_jaffle_orders"]


def test_the_gate_returns_the_report_of_an_invalid_repo(jaffle_repo: Path):
    (jaffle_repo / "dataproducts/sa_jaffle_orders/src/orders.py").unlink()
    report = plan_repo(jaffle_repo)
    assert isinstance(report, Report)
    assert "does not exist" in report.problems[0].message


def test_validate_plans_the_data_products_once_with_every_stage_two_check_running(
    jaffle_dbt_repo: Path, plan_calls: list[int]
):
    write(jaffle_dbt_repo, "target/manifest.json", MANIFEST)
    (jaffle_dbt_repo / "dbt_project.yml").write_text("name: jaffle_shop\nversion: '1.0'\nprofile: jaffle_shop\n")
    (jaffle_dbt_repo / "dataproducts/agg_weekly_orders/models/_group.yml").unlink()
    problems = validate_repo(jaffle_dbt_repo).problems
    assert any("dbt properties file is missing" in problem.message for problem in problems)  # the dbt diff ran
    assert len(plan_calls) == 1


def test_generate_plans_the_data_products_once(jaffle_dbt_repo: Path, plan_calls: list[int]):
    (jaffle_dbt_repo / "dbt_project.yml").write_text("name: jaffle_shop\nversion: '1.0'\nprofile: jaffle_shop\n")
    assert generate_repo(jaffle_dbt_repo).report.ok
    assert len(plan_calls) == 1


def test_generate_needs_no_dbt_manifest(jaffle_dbt_repo: Path):
    (jaffle_dbt_repo / "dbt_project.yml").write_text("name: jaffle_shop\nversion: '1.0'\nprofile: jaffle_shop\n")
    assert not (jaffle_dbt_repo / "target").exists()
    assert generate_repo(jaffle_dbt_repo).report.ok


def test_validate_reports_a_render_failure_and_a_dbt_file_problem_in_one_run(jaffle_dbt_repo: Path):
    write(jaffle_dbt_repo, "target/manifest.json", MANIFEST)
    (jaffle_dbt_repo / "dataproducts/agg_weekly_orders/models/_group.yml").unlink()
    port = jaffle_dbt_repo / "dataproducts/agg_weekly_orders/outputs/agg_weekly_orders"
    (port / "dbt.yaml").write_text((port / "weekly.yaml").read_text().replace("name: weekly", "name: dbt"))
    messages = [problem.message for problem in validate_repo(jaffle_dbt_repo).problems]
    assert any("used twice" in message for message in messages)
    assert any("dbt properties file is missing" in message for message in messages)
