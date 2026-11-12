"""A runtime is chosen by the render kind of the orchestrator, never by the orchestrator's name."""

import ast
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

import pytest
from container_helpers import table_of
from plugin_fakes import register

from datapatchbay.generate import generate_repo
from datapatchbay.integrations._codegen.table_builds import plan_builds, render_build
from datapatchbay.integrations.python.executor import PythonExecutor
from datapatchbay.integrations.worker.runtime import WorkerRuntime
from datapatchbay.plugins import (
    BuildTask,
    DataProductPlan,
    GeneratedFile,
    GenerationContext,
    RenderKind,
    UnsupportedCombinationError,
)


class ThirdPartyOrchestrator:
    """An orchestrator that is not in this package: it asks each runtime for a plain function per Python table."""

    render_kind: RenderKind = "function"

    def generate(self, plan: DataProductPlan, context: GenerationContext) -> Sequence[GeneratedFile]:
        builds = plan_builds(plan, context)
        lines: list[str] = []
        for table in builds.python_tables:
            rendered = render_build(
                context,
                plan.orchestrator,
                self.render_kind,
                table,
                builds.calls[table.name],
                task_id=f"build_{table.name}",
                where=f"table '{table.name}'",
                variable=f"build_{table.name}",
            )
            lines.extend([*rendered.imports, *rendered.helpers, *rendered.lines])
        text = "DATAPRODUCT_DIR = None\n" + "\n".join(lines) + "\n"
        return [GeneratedFile(PurePosixPath(f"{plan.folder}.py"), text)]


def test_a_third_party_orchestrator_of_kind_function_works_with_the_worker_runtime(
    jaffle_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    register(monkeypatch, "orchestrator", "thirdparty", ThirdPartyOrchestrator)
    product = jaffle_repo / "dataproducts/sa_jaffle_orders/dataproduct.yaml"
    product.write_text(product.read_text() + "orchestrator: thirdparty\n")

    result = generate_repo(jaffle_repo)

    assert result.report.ok, result.report.problems
    text = (jaffle_repo / "generated/sa_jaffle_orders.py").read_text()
    ast.parse(text)
    assert "def _build_function(" in text
    assert "build_ingested_orders = _build_function(" in text
    assert "airflow" not in text


def test_a_runtime_that_only_renders_tasks_is_refused_on_an_orchestrator_of_kind_function(
    jaffle_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    register(monkeypatch, "orchestrator", "thirdparty", ThirdPartyOrchestrator)
    product = jaffle_repo / "dataproducts/agg_weekly_orders/dataproduct.yaml"
    product.write_text(product.read_text() + "orchestrator: thirdparty\n")  # its tables run on docker

    result = generate_repo(jaffle_repo)

    assert any(
        "the docker runtime cannot render tasks for orchestrator 'thirdparty'" in problem.message
        for problem in result.report.problems
    )


def test_the_worker_runtime_refuses_a_kind_it_does_not_know(jaffle_repo: Path):
    table = table_of(jaffle_repo)
    task = BuildTask("build_x", table, PythonExecutor().call(table))
    with pytest.raises(UnsupportedCombinationError, match="kind 'coroutine'"):
        WorkerRuntime().render_build_task(task, kind="coroutine", variable="x")  # ty: ignore[invalid-argument-type]
