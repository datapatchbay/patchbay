import importlib.util
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from container_helpers import table_of

from datapatchbay.builtin.dbt_executor import DbtExecutor
from datapatchbay.builtin.python_executor import PythonExecutor
from datapatchbay.builtin.worker import FUNCTION_ORCHESTRATORS, WorkerRuntime
from datapatchbay.plugins import BuildTask, RenderedTask

PRODUCT = "dataproducts/sa_jaffle_orders"


def run(rendered: RenderedTask, namespace: dict[str, Any]) -> Any:
    """Run the rendered helpers and lines the way a generated file does, and return what `build` was assigned."""
    exec("\n\n".join(rendered.helpers), namespace)
    exec("\n".join(rendered.lines), namespace)
    return namespace["build"]


@pytest.mark.parametrize("orchestrator", sorted(FUNCTION_ORCHESTRATORS))
def test_the_worker_renders_a_function_that_calls_the_entrypoint_with_the_params(jaffle_repo: Path, orchestrator: str):
    product = jaffle_repo / PRODUCT
    (product / "src/ingested.py").write_text(
        "from pathlib import Path\n\n\n"
        "def build(limit):\n"
        "    Path(__file__).with_name('called.txt').write_text(str(limit))\n"
    )
    table = table_of(jaffle_repo)
    task = BuildTask("build_ingested_orders", table, PythonExecutor().call(table))

    rendered = WorkerRuntime().render_build_task(task, orchestrator=orchestrator, variable="build")

    assert rendered.imports == ("import importlib.util",)
    assert rendered.lines == (
        'build = _build_function("build_ingested_orders", "src/ingested.py", "build", {"limit": 100})',
    )
    build = run(rendered, {"importlib": importlib, "DATAPRODUCT_DIR": product})
    assert not (product / "src/called.txt").exists()  # nothing runs until the orchestrator calls the function
    build()
    assert (product / "src/called.txt").read_text() == "100"


def test_the_function_of_the_worker_raises_when_the_build_raises(jaffle_repo: Path):
    product = jaffle_repo / PRODUCT
    (product / "src/ingested.py").write_text("def build(limit):\n    raise RuntimeError('no source')\n")
    table = table_of(jaffle_repo)
    task = BuildTask("build_ingested_orders", table, PythonExecutor().call(table))
    rendered = WorkerRuntime().render_build_task(task, orchestrator="local", variable="build")
    build = run(rendered, {"importlib": importlib, "DATAPRODUCT_DIR": product})
    with pytest.raises(RuntimeError, match="no source"):
        build()


def test_the_worker_renders_a_function_that_runs_dbt_build_in_the_project(
    jaffle_dbt_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    runs: list[tuple[list[str], Path]] = []

    def fake_run(command: list[str], *, check: bool, cwd: Path) -> None:
        assert check
        runs.append((command, cwd))

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("HOME", "/home/worker")
    table = table_of(jaffle_dbt_repo, "weekly_summary")
    task = BuildTask("build_dbt", table, DbtExecutor().call(table))
    product = jaffle_dbt_repo / "dataproducts/agg_weekly_orders"

    rendered = WorkerRuntime().render_build_task(task, orchestrator="local", variable="build")

    assert rendered.imports == ("import os", "import subprocess")
    assert rendered.lines == (
        'build = _dbt_build_function("../..", "~/.dbt", "dataproducts/agg_weekly_orders/models")',
    )
    build = run(rendered, {"os": os, "subprocess": subprocess, "DATAPRODUCT_DIR": product})
    assert runs == []
    build()
    project = jaffle_dbt_repo.resolve()
    assert runs == [
        (
            [
                "dbt",
                "build",
                "--project-dir",
                str(project),
                "--profiles-dir",
                "/home/worker/.dbt",
                "--select",
                "path:dataproducts/agg_weekly_orders/models",
            ],
            project,
        )
    ]
