import os
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from plan_helpers import plan_all

from datapatchbay.integrations.airflow.orchestrator import AirflowOrchestrator
from datapatchbay.integrations.dbt.executor import DbtExecutor
from datapatchbay.integrations.docker.runtime import DockerRuntime
from datapatchbay.integrations.kubernetes.runtime import KubernetesRuntime
from datapatchbay.integrations.python.executor import PythonExecutor
from datapatchbay.integrations.worker.runtime import WorkerRuntime
from datapatchbay.loading import load_repo
from datapatchbay.plugins import BuildTask, DataProductPlan, GenerationContext, UnsupportedCombinationError


def plan_of(root: Path, folder: str) -> DataProductPlan:
    repo, problems = load_repo(root)
    assert problems == []
    plans = plan_all(repo, root)
    return next(plan for plan in plans if plan.folder == folder)


def context_of(root: Path) -> GenerationContext:
    return GenerationContext(
        root=root,
        output_dir=root / "generated",
        executors={"python": PythonExecutor(), "dbt": DbtExecutor()},
        runtimes={"worker": WorkerRuntime(), "docker": DockerRuntime(), "kubernetes": KubernetesRuntime()},
    )


def test_a_data_product_folder_that_is_not_an_airflow_id_is_refused(jaffle_repo: Path):
    plan = replace(plan_of(jaffle_repo, "sa_jaffle_orders"), folder="sa jaffle orders")
    with pytest.raises(
        UnsupportedCombinationError, match=r"data product 'sa jaffle orders' .* is not a valid Airflow id"
    ):
        AirflowOrchestrator().generate(plan, context_of(jaffle_repo))


def test_an_output_port_name_that_is_not_an_airflow_id_is_refused(jaffle_repo: Path):
    plan = replace(plan_of(jaffle_repo, "sa_jaffle_orders"), outputs=("sa/jaffle/orders",))
    with pytest.raises(UnsupportedCombinationError, match=r"port 'sa/jaffle/orders' \(asset name\) is not a valid"):
        AirflowOrchestrator().generate(plan, context_of(jaffle_repo))


def test_the_python_executor_calls_the_entrypoint_function_with_the_params(jaffle_repo: Path):
    ingested = plan_of(jaffle_repo, "sa_jaffle_orders").tables[0]
    call = PythonExecutor().call(ingested)
    assert (str(call.file), call.function, dict(call.params)) == ("src/ingested.py", "build", {"limit": 100})


def dbt_task_of(root: Path) -> BuildTask:
    weekly = plan_of(root, "agg_weekly_orders")
    table = next(t for t in weekly.tables if t.executor == "dbt")
    return BuildTask("build_dbt", table, DbtExecutor().call(table))


def test_the_worker_runs_dbt_build_on_the_models_folder_with_the_project_and_profiles_of_the_settings(
    jaffle_dbt_repo: Path,
):
    rendered = WorkerRuntime().render_build_task(dbt_task_of(jaffle_dbt_repo), kind="task", variable="dbt")
    assert rendered.imports == ("import os", "import subprocess", "from airflow.sdk import task")
    assert rendered.lines == (
        'dbt = _command_task("build_dbt", ["dbt", "build", "--select", '
        '"path:dataproducts/agg_weekly_orders/models", "--project-dir", ".", "--profiles-dir", "~/.dbt"], '
        '"../..", {})',
    )
    [helper] = rendered.helpers
    assert "os.path.expanduser(argument) for argument in argv" in helper
    assert "subprocess.run(command, check=True, cwd=(DATAPRODUCT_DIR / cwd).resolve()" in helper


@pytest.mark.parametrize("runtime", [DockerRuntime(), KubernetesRuntime()])
def test_container_runtimes_refuse_a_dbt_build_and_say_to_use_another_runtime(jaffle_dbt_repo: Path, runtime):
    with pytest.raises(UnsupportedCombinationError, match=r"cannot run a CommandCall: set a runtime that can"):
        runtime.render_build_task(dbt_task_of(jaffle_dbt_repo), kind="task", variable="dbt")


def test_the_dbt_executor_fails_for_a_table_without_a_dbt_location(jaffle_dbt_repo: Path):
    table = replace(dbt_task_of(jaffle_dbt_repo).table, dbt=None)
    with pytest.raises(UnsupportedCombinationError, match="table 'weekly_summary' has no dbt location"):
        DbtExecutor().call(table)


def test_a_python_table_cannot_need_a_table_that_dbt_builds(jaffle_dbt_repo: Path):
    plan = plan_of(jaffle_dbt_repo, "agg_weekly_orders")
    tables = tuple(replace(t, needs=("weekly_summary",)) if t.name == "weekly_pod" else t for t in plan.tables)
    with pytest.raises(UnsupportedCombinationError, match="table 'weekly_pod' needs table 'weekly_summary', which dbt"):
        AirflowOrchestrator().generate(replace(plan, tables=tables), context_of(jaffle_dbt_repo))


def test_tables_built_by_dbt_in_one_task_need_the_same_runtime(jaffle_dbt_repo: Path):
    plan = plan_of(jaffle_dbt_repo, "agg_weekly_orders")
    first = next(t for t in plan.tables if t.executor == "dbt")
    second = replace(first, name="other", runtime="docker")
    with pytest.raises(UnsupportedCombinationError, match="'weekly_summary' and 'other' are built by dbt in one task"):
        AirflowOrchestrator().generate(replace(plan, tables=(*plan.tables, second)), context_of(jaffle_dbt_repo))


def test_a_data_product_with_only_dbt_tables_has_just_the_dbt_task_before_the_publish(jaffle_dbt_repo: Path):
    plan = plan_of(jaffle_dbt_repo, "agg_weekly_orders")
    tables = tuple(t for t in plan.tables if t.executor == "dbt")
    [file] = AirflowOrchestrator().generate(replace(plan, tables=tables), context_of(jaffle_dbt_repo))
    body = file.content.split("with DAG(", 1)[1]
    assert body.count("_command_task(") == 1
    assert "build_weekly" not in body
    assert "    build_dbt >> publish\n" in body


def test_the_dbt_task_runs_the_dbt_command_in_the_project(
    jaffle_dbt_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runs: list[tuple[list[str], Path]] = []

    def fake_run(command: list[str], *, check: bool, cwd: Path, env: dict[str, str]) -> None:
        assert check
        runs.append((command, cwd))

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("HOME", "/home/airflow")
    rendered = WorkerRuntime().render_build_task(dbt_task_of(jaffle_dbt_repo), kind="task", variable="dbt")
    product = jaffle_dbt_repo / "dataproducts/agg_weekly_orders"
    # Airflow's `task` turns the function into an operator; here it just hands the function back when called.
    namespace: dict[str, Any] = {
        "os": os,
        "subprocess": subprocess,
        "task": lambda task_id: lambda function: lambda: function,
        "DATAPRODUCT_DIR": product,
    }
    exec(rendered.helpers[0], namespace)  # the generated file is plain Python
    exec(rendered.lines[0], namespace)
    namespace["dbt"]()
    assert runs == [
        (
            [
                "dbt",
                "build",
                "--select",
                "path:dataproducts/agg_weekly_orders/models",
                "--project-dir",
                ".",
                "--profiles-dir",
                "/home/airflow/.dbt",
            ],
            jaffle_dbt_repo.resolve(),
        )
    ]
