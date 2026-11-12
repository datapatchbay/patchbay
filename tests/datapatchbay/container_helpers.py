from pathlib import Path

from plan_helpers import plan_all

from datapatchbay.files.loading import load_repo
from datapatchbay.integrations.docker.runtime import DockerRuntime
from datapatchbay.integrations.kubernetes.runtime import KubernetesRuntime
from datapatchbay.integrations.python.executor import PythonExecutor
from datapatchbay.plugins import BuildTask, RenderedTask, TablePlan


def table_of(root: Path, name: str = "ingested_orders") -> TablePlan:
    repo, problems = load_repo(root)
    assert problems == []
    plans = plan_all(repo, root)
    return next(t for plan in plans for t in plan.tables if t.name == name)


def render(runtime: DockerRuntime | KubernetesRuntime, table: TablePlan) -> RenderedTask:
    task = BuildTask(f"build_{table.name}", table, PythonExecutor().call(table))
    return runtime.render_build_task(task, kind="task", variable="build")
