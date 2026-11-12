from pathlib import Path

import pytest
from audit_support import audit_of, columns_yaml

from datapatchbay.builtin.duckdb import DuckDbWarehouse
from datapatchbay.generate import generate_repo
from datapatchbay.loading import load_repo
from datapatchbay.planning import plan_dataproducts
from datapatchbay.settings import load_settings

RULES = (
    columns_yaml(
        order_id_rules="- not_null\n- {rule: unique, severity: warning}\n- {rule: not_null, severity: none}\n",
        status_rules="- {rule: accepted_values, values: [a]}\n",
    )
    + "rules:\n  - {rule: row_count, min: 1}\n  - {rule: primary_key, columns: [order_id]}\n"
)


def test_duckdb_audits_with_the_same_task_id_rules_and_severities_as_postgres(jaffle_repo: Path):
    on_duckdb = audit_of(jaffle_repo, RULES, warehouse=DuckDbWarehouse())
    on_postgres = audit_of(jaffle_repo, RULES)
    assert on_duckdb is not None
    assert on_postgres is not None
    assert on_duckdb.task_id == "audit_orders"
    assert [(c.rule, c.table, c.column, c.severity) for c in on_duckdb.checks] == [
        (c.rule, c.table, c.column, c.severity) for c in on_postgres.checks
    ]
    assert [c.rule for c in on_duckdb.checks] == [
        "not_null",
        "unique",
        "accepted_values",
        "row_count",
        "primary_key",
    ]


def test_a_table_without_rules_gets_no_audit_task_on_duckdb(jaffle_repo: Path):
    assert audit_of(jaffle_repo, columns_yaml(), warehouse=DuckDbWarehouse()) is None


def test_a_table_built_by_dbt_gets_no_audit_task_on_duckdb(jaffle_dbt_repo: Path):
    repo, problems = load_repo(jaffle_dbt_repo)
    assert problems == []
    plan = next(p for p in plan_dataproducts(repo, load_settings(jaffle_dbt_repo)) if p.folder == "agg_weekly_orders")
    table = next(t for t in plan.tables if t.executor == "dbt")
    assert table.source.file.model.columns[0].rules
    assert DuckDbWarehouse().audit_tasks(table) == ()


def test_duckdb_returns_no_apply_tasks_because_views_are_not_generated_yet(jaffle_repo: Path):
    repo, _ = load_repo(jaffle_repo)
    plan = next(p for p in plan_dataproducts(repo, load_settings(jaffle_repo)) if p.folder == "sa_jaffle_orders")
    assert DuckDbWarehouse().apply_tasks(plan) == ()


@pytest.mark.parametrize("name", ["duckdb", "postgres"])
def test_generate_writes_the_audit_task_of_each_table_with_rules_and_no_access_task_on_duckdb(
    jaffle_repo: Path, name: str
):
    (jaffle_repo / "datapatchbay.yaml").write_text(f"schema_version: 1\nwarehouse: {name}\n")
    result = generate_repo(jaffle_repo)
    assert result.report.ok
    dag = (jaffle_repo / "generated/sa_jaffle_orders.py").read_text()
    assert '_audit_task("audit_orders"' in dag
    assert ("apply_access" in dag) == (name == "postgres")
