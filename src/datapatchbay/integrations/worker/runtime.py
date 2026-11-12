"""The `worker` runtime: the entrypoint is called on the orchestrator's worker, in the worker's environment.

For the render kind `task` the build is rendered as an Airflow task. For the render kind `function`, used by the
orchestrators whose generated file is plain Python, it is rendered as a function with no arguments, which the
orchestrator calls when the build has to run.
"""

from datapatchbay.plugins import (
    BuildTask,
    CommandCall,
    PythonCall,
    RenderedTask,
    RenderKind,
    UnsupportedCombinationError,
)
from datapatchbay.plugins.codegen import python_literal

_AIRFLOW_HELPER = '''\
def _build_task(task_id, path, function, params):
    """Create a task that loads a file of the data product and calls a function in it."""

    @task(task_id=task_id)
    def build():
        spec = importlib.util.spec_from_file_location(f"datapatchbay_{task_id}", DATAPRODUCT_DIR / path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        getattr(module, function)(**params)

    return build()'''

_AIRFLOW_COMMAND_HELPER = '''\
def _command_task(task_id, argv, cwd, env, home_args):
    """Create a task that runs a command on the worker."""

    @task(task_id=task_id)
    def build():
        command = [os.path.expanduser(a) if i in home_args else a for i, a in enumerate(argv)]
        subprocess.run(command, check=True, cwd=(DATAPRODUCT_DIR / cwd).resolve(), env={**os.environ, **env})

    return build()'''

_FUNCTION_HELPER = '''\
def _build_function(task_id, path, function, params):
    """Return a function that loads a file of the data product and calls a function in it."""

    def build():
        spec = importlib.util.spec_from_file_location(f"datapatchbay_{task_id}", DATAPRODUCT_DIR / path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        getattr(module, function)(**params)

    return build'''

_FUNCTION_COMMAND_HELPER = '''\
def _command_function(argv, cwd, env, home_args):
    """Return a function that runs a command on the worker."""

    def build():
        command = [os.path.expanduser(a) if i in home_args else a for i, a in enumerate(argv)]
        subprocess.run(command, check=True, cwd=(DATAPRODUCT_DIR / cwd).resolve(), env={**os.environ, **env})

    return build'''


class WorkerRuntime:
    """Call the entrypoint in the orchestrator's own process, so it runs on the worker."""

    needs_image = False
    call_types: tuple[type, ...] = (PythonCall, CommandCall)
    render_kinds: frozenset[RenderKind] = frozenset({"task", "function"})

    def render_build_task(self, task: BuildTask, *, kind: RenderKind, variable: str) -> RenderedTask:
        """Render a task that calls the function, or runs the command of a `CommandCall` on the worker.

        The module is imported when the build runs, not while the orchestrator loads the file; a command is run as a
        subprocess of the worker, with the working directory and environment of the call.

        For the kind `task`, `variable` is assigned an Airflow task. For the kind `function` it is assigned a
        function with no arguments that runs the build and raises when the build fails. In both cases the
        generated file must define `DATAPRODUCT_DIR`, the data product folder.

        Raises:
            UnsupportedCombinationError: If the kind is not one of `render_kinds`.
            ValueError: If a param is not a plain YAML value.
        """
        if kind == "task":
            return _airflow_task(task, variable)
        if kind == "function":
            return _plain_function(task, variable)
        raise UnsupportedCombinationError(f"the worker runtime cannot render tasks of kind '{kind}'")


def _command_arguments(call: CommandCall) -> list[str]:
    return [
        python_literal(list(call.argv)),
        python_literal(call.cwd),
        python_literal(dict(sorted(call.env.items()))),
        python_literal(list(call.home_args)),
    ]


def _python_arguments(task: BuildTask, call: PythonCall) -> list[str]:
    return [
        python_literal(task.task_id),
        python_literal(call.file.as_posix()),
        python_literal(call.function),
        python_literal(call.params),
    ]


def _airflow_task(task: BuildTask, variable: str) -> RenderedTask:
    call = task.call
    if isinstance(call, CommandCall):
        arguments = ", ".join([python_literal(task.task_id), *_command_arguments(call)])
        return RenderedTask(
            imports=("import os", "import subprocess", "from airflow.sdk import task"),
            helpers=(_AIRFLOW_COMMAND_HELPER,),
            lines=(f"{variable} = _command_task({arguments})",),
        )
    return RenderedTask(
        imports=("import importlib.util", "from airflow.sdk import task"),
        helpers=(_AIRFLOW_HELPER,),
        lines=(f"{variable} = _build_task({', '.join(_python_arguments(task, call))})",),
    )


def _plain_function(task: BuildTask, variable: str) -> RenderedTask:
    call = task.call
    if isinstance(call, CommandCall):
        return RenderedTask(
            imports=("import os", "import subprocess"),
            helpers=(_FUNCTION_COMMAND_HELPER,),
            lines=(f"{variable} = _command_function({', '.join(_command_arguments(call))})",),
        )
    return RenderedTask(
        imports=("import importlib.util",),
        helpers=(_FUNCTION_HELPER,),
        lines=(f"{variable} = _build_function({', '.join(_python_arguments(task, call))})",),
    )
