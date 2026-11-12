from dataclasses import replace
from pathlib import Path

import pytest

from datapatchbay.builtin.airflow import AirflowOrchestrator
from datapatchbay.builtin.python_executor import PythonExecutor
from datapatchbay.builtin.worker import WorkerRuntime
from datapatchbay.loading import load_repo
from datapatchbay.planning import plan_dataproducts
from datapatchbay.plugins import BuildTask, DataProductPlan, GenerationContext, UnsupportedCombinationError
from datapatchbay.settings import load_settings


def plan_of(root: Path, folder: str) -> DataProductPlan:
    repo, problems = load_repo(root)
    assert problems == []
    plans = plan_dataproducts(repo, load_settings(root))
    return next(plan for plan in plans if plan.folder == folder)


def context_of(root: Path) -> GenerationContext:
    return GenerationContext(
        root=root,
        output_dir=root / "generated",
        executors={"python": PythonExecutor()},
        runtimes={"worker": WorkerRuntime()},
    )


def test_a_data_product_folder_that_is_not_an_airflow_id_is_refused(lab_repo: Path):
    plan = replace(plan_of(lab_repo, "sa_ilab_orders"), folder="sa ilab orders")
    with pytest.raises(
        UnsupportedCombinationError, match=r"data product 'sa ilab orders' .* is not a valid Airflow id"
    ):
        AirflowOrchestrator().generate(plan, context_of(lab_repo))


def test_an_output_port_name_that_is_not_an_airflow_id_is_refused(lab_repo: Path):
    plan = replace(plan_of(lab_repo, "sa_ilab_orders"), outputs=("sa/ilab/orders",))
    with pytest.raises(UnsupportedCombinationError, match=r"port 'sa/ilab/orders' \(asset name\) is not a valid"):
        AirflowOrchestrator().generate(plan, context_of(lab_repo))


def test_the_worker_runtime_only_renders_for_airflow(lab_repo: Path):
    plan = plan_of(lab_repo, "sa_ilab_orders")
    table = plan.tables[0]
    task = BuildTask("build_x", table, PythonExecutor().call(table))
    with pytest.raises(UnsupportedCombinationError, match="orchestrator 'prefect'"):
        WorkerRuntime().render_build_task(task, orchestrator="prefect", variable="x")


def test_the_python_executor_calls_the_entrypoint_function_with_the_params(lab_repo: Path):
    ingested = plan_of(lab_repo, "sa_ilab_orders").tables[0]
    call = PythonExecutor().call(ingested)
    assert (str(call.file), call.function, dict(call.params)) == ("src/ingested.py", "build", {"limit": 100})
