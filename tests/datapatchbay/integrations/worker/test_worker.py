import importlib.util
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from container_helpers import table_of

from datapatchbay.integrations.python.executor import PythonExecutor
from datapatchbay.integrations.worker.runtime import WorkerRuntime
from datapatchbay.plugins import BuildTask, CommandCall, RenderedTask

PRODUCT = "dataproducts/sa_jaffle_orders"


def run(rendered: RenderedTask, namespace: dict[str, Any]) -> Any:
    """Run the rendered helpers and lines the way a generated file does, and return what `build` was assigned."""
    exec("\n\n".join(rendered.helpers), namespace)
    exec("\n".join(rendered.lines), namespace)
    return namespace["build"]


def test_the_worker_renders_a_function_that_calls_the_entrypoint_with_the_params(jaffle_repo: Path):
    product = jaffle_repo / PRODUCT
    (product / "src/ingested.py").write_text(
        "from pathlib import Path\n\n\n"
        "def build(limit):\n"
        "    Path(__file__).with_name('called.txt').write_text(str(limit))\n"
    )
    table = table_of(jaffle_repo)
    task = BuildTask("build_ingested_orders", table, PythonExecutor().call(table))

    rendered = WorkerRuntime().render_build_task(task, kind="function", variable="build")

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
    rendered = WorkerRuntime().render_build_task(task, kind="function", variable="build")
    build = run(rendered, {"importlib": importlib, "DATAPRODUCT_DIR": product})
    with pytest.raises(RuntimeError, match="no source"):
        build()


def test_the_worker_renders_a_function_that_runs_a_command_in_its_working_directory(
    jaffle_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runs: list[tuple[list[str], Path, dict[str, str]]] = []

    def fake_run(command: list[str], *, check: bool, cwd: Path, env: dict[str, str]) -> None:
        assert check
        runs.append((command, cwd, env))

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("HOME", "/home/worker")
    monkeypatch.setenv("KEPT", "yes")
    product = tmp_path / "dataproducts/orders"
    product.mkdir(parents=True)
    call = CommandCall(argv=("tool", "--config", "~/.tool", "--flag=~"), cwd="../..", env={"MODE": "fast"})
    task = BuildTask("build_tool", table_of(jaffle_repo), call)

    rendered = WorkerRuntime().render_build_task(task, kind="function", variable="build")

    assert rendered.imports == ("import os", "import subprocess")
    assert rendered.lines == (
        'build = _command_function(["tool", "--config", "~/.tool", "--flag=~"], "../..", {"MODE": "fast"})',
    )
    build = run(rendered, {"os": os, "subprocess": subprocess, "DATAPRODUCT_DIR": product})
    assert runs == []
    build()
    [(command, cwd, env)] = runs
    assert command == ["tool", "--config", "/home/worker/.tool", "--flag=~"]  # only a leading ~ is expanded
    assert cwd == tmp_path.resolve()
    assert env["MODE"] == "fast"
    assert env["KEPT"] == "yes"  # the environment of the worker stays


def test_the_worker_resolves_an_absolute_working_directory_as_it_is(jaffle_repo: Path, tmp_path: Path):
    call = CommandCall(argv=("tool",), cwd=str(tmp_path))
    task = BuildTask("build_tool", table_of(jaffle_repo), call)
    rendered = WorkerRuntime().render_build_task(task, kind="task", variable="tool")
    assert rendered.lines == (f'tool = _command_task("build_tool", ["tool"], "{tmp_path}", {{}})',)
