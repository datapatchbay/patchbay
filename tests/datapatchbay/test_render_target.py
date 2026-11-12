"""A runtime is chosen by the render kind of the orchestrator, never by the orchestrator's name."""

import ast
from pathlib import Path

import pytest
from container_helpers import table_of
from plugin_fakes import ThirdPartyOrchestrator, install_distribution, register

from datapatchbay.generate import generate_repo
from datapatchbay.integrations.python.executor import PythonExecutor
from datapatchbay.integrations.worker.runtime import WorkerRuntime
from datapatchbay.plugins import (
    BuildTask,
    UnsupportedCombinationError,
)


def test_a_third_party_orchestrator_of_kind_function_works_with_the_worker_runtime(
    jaffle_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    install_distribution(
        monkeypatch, tmp_path / "site", "orchestrator", "thirdparty", "plugin_fakes:ThirdPartyOrchestrator"
    )
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
