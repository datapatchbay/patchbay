"""How the orchestrators share the build of a table: one by one, or in a batch of an executor that builds together."""

from dataclasses import replace
from pathlib import Path

import pytest
from plan_helpers import plan_all
from plugin_fakes import FakeWarehouse

from datapatchbay.integrations.dbt.executor import DbtExecutor
from datapatchbay.integrations.python.executor import PythonExecutor
from datapatchbay.loading import load_repo
from datapatchbay.plugins import DataProductPlan, GenerationContext, UnsupportedCombinationError
from datapatchbay.plugins.codegen import plan_builds, warehouse_audits


class OtherBatchExecutor(DbtExecutor):
    """An executor with another `batch_key`, that is not dbt, to have two batches in one data product."""

    batch_key = "other"


def weekly_orders(root: Path) -> DataProductPlan:
    repo, problems = load_repo(root)
    assert problems == []
    return next(plan for plan in plan_all(repo, root) if plan.folder == "agg_weekly_orders")


def context(root: Path, **extra: object) -> GenerationContext:
    executors = {"dbt": DbtExecutor(), "python": PythonExecutor(), "other": OtherBatchExecutor()}
    return GenerationContext(root=root, output_dir=root / "out", executors=executors, **extra)  # ty: ignore[invalid-argument-type]


def with_executor(plan: DataProductPlan, name: str, executor: str) -> DataProductPlan:
    tables = tuple(replace(t, executor=executor) if t.name == name else t for t in plan.tables)
    return replace(plan, tables=tables)


def test_the_tables_of_a_batch_are_one_batch_named_after_the_key_of_the_executor(jaffle_dbt_repo: Path):
    plan = weekly_orders(jaffle_dbt_repo)
    builds = plan_builds(plan, context(jaffle_dbt_repo))
    assert [b.key for b in builds.batches] == ["dbt"]
    batch = builds.batches[0]
    assert (batch.task_id, batch.where) == ("build_dbt", "tables built by dbt")
    assert {t.executor for t in batch.tables} == {"dbt"}
    assert {t.name for t in builds.python_tables}.isdisjoint(t.name for t in batch.tables)
    assert batch.call == builds.calls[batch.tables[0].name]


def test_each_executor_with_its_own_key_builds_its_own_batch_sorted_by_key(jaffle_dbt_repo: Path):
    plan = weekly_orders(jaffle_dbt_repo)
    dbt_table = next(t for t in plan.tables if t.executor == "dbt")
    # Two dbt tables in two batches: the second table is a copy that the other executor builds.
    other = replace(dbt_table, name="copy", needs=(), executor="other")
    plan = replace(plan, tables=(*plan.tables, other))
    builds = plan_builds(plan, context(jaffle_dbt_repo))
    assert [(b.key, [t.name for t in b.tables]) for b in builds.batches] == [
        ("dbt", [dbt_table.name]),
        ("other", ["copy"]),
    ]


def test_a_table_cannot_need_a_table_of_a_batch_it_is_not_in(jaffle_dbt_repo: Path):
    plan = weekly_orders(jaffle_dbt_repo)
    dbt_table = next(t for t in plan.tables if t.executor == "dbt")
    python_table = next(t for t in plan.tables if t.executor == "python")
    needy = replace(python_table, needs=(dbt_table.name,))
    plan = replace(plan, tables=tuple(needy if t.name == python_table.name else t for t in plan.tables))
    with pytest.raises(
        UnsupportedCombinationError, match=r"which dbt builds after the Python tables; dbt tables cannot"
    ):
        plan_builds(plan, context(jaffle_dbt_repo))


def test_the_tables_of_a_batch_must_share_a_runtime(jaffle_dbt_repo: Path):
    plan = weekly_orders(jaffle_dbt_repo)
    dbt_table = next(t for t in plan.tables if t.executor == "dbt")
    plan = replace(plan, tables=(*plan.tables, replace(dbt_table, name="copy", needs=(), runtime="docker")))
    with pytest.raises(UnsupportedCombinationError, match=r"are built by dbt in one task, but their runtimes are"):
        plan_builds(plan, context(jaffle_dbt_repo))


def test_the_warehouse_audits_a_table_unless_its_executor_runs_the_rules_itself(jaffle_dbt_repo: Path):
    plan = weekly_orders(jaffle_dbt_repo)
    ctx = context(jaffle_dbt_repo, warehouse=FakeWarehouse())
    dbt_table = next(t for t in plan.tables if t.executor == "dbt")
    python_table = next(t for t in plan.tables if t.executor == "python")
    assert warehouse_audits(ctx, dbt_table) == ()
    assert [a.task_id for a in warehouse_audits(ctx, python_table)] == [f"audit_{python_table.name}"]


def test_without_a_warehouse_a_table_has_no_audits(jaffle_dbt_repo: Path):
    plan = weekly_orders(jaffle_dbt_repo)
    python_table = next(t for t in plan.tables if t.executor == "python")
    assert warehouse_audits(context(jaffle_dbt_repo), python_table) == ()
