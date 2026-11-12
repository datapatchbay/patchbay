"""The `worker` runtime: the entrypoint is called on the orchestrator's worker, in the worker's environment.

For the render kind `task` the build is rendered as an Airflow task. For the render kind `function`, used by the
orchestrators whose generated file is plain Python, it is rendered as a function with no arguments, which the
orchestrator calls when the build has to run.
"""

from datapatchbay.plugins import BuildTask, DbtCall, PythonCall, RenderedTask, RenderKind, UnsupportedCombinationError
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

_AIRFLOW_DBT_HELPER = '''\
def _dbt_build_task(task_id, project_dir, profiles_dir, select):
    """Create a task that runs `dbt build` on the models in a folder of the dbt project."""

    @task(task_id=task_id)
    def build():
        project = (DATAPRODUCT_DIR / project_dir).resolve()
        command = [
            "dbt",
            "build",
            "--project-dir",
            str(project),
            "--profiles-dir",
            os.path.expanduser(profiles_dir),
            "--select",
            f"path:{select}",
        ]
        subprocess.run(command, check=True, cwd=project)

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

_FUNCTION_DBT_HELPER = '''\
def _dbt_build_function(project_dir, profiles_dir, select):
    """Return a function that runs `dbt build` on the models in a folder of the dbt project."""

    def build():
        project = (DATAPRODUCT_DIR / project_dir).resolve()
        command = [
            "dbt",
            "build",
            "--project-dir",
            str(project),
            "--profiles-dir",
            os.path.expanduser(profiles_dir),
            "--select",
            f"path:{select}",
        ]
        subprocess.run(command, check=True, cwd=project)

    return build'''


class WorkerRuntime:
    """Call the entrypoint in the orchestrator's own process, so it runs on the worker."""

    needs_image = False
    call_types: tuple[type, ...] = (PythonCall, DbtCall)
    render_kinds: frozenset[RenderKind] = frozenset({"task", "function"})

    def render_build_task(self, task: BuildTask, *, kind: RenderKind, variable: str) -> RenderedTask:
        """Render a task that calls the function, or runs `dbt build` on the worker for a `DbtCall`.

        The module is imported when the build runs, not while the orchestrator loads the file; `dbt` is run as a
        command of the worker.

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


def _dbt_arguments(call: DbtCall) -> list[str]:
    return [python_literal(value) for value in (call.project_dir, call.profiles_dir, str(call.select))]


def _python_arguments(task: BuildTask, call: PythonCall) -> list[str]:
    return [
        python_literal(task.task_id),
        python_literal(call.file.as_posix()),
        python_literal(call.function),
        python_literal(call.params),
    ]


def _airflow_task(task: BuildTask, variable: str) -> RenderedTask:
    call = task.call
    if isinstance(call, DbtCall):
        arguments = ", ".join([python_literal(task.task_id), *_dbt_arguments(call)])
        return RenderedTask(
            imports=("import os", "import subprocess", "from airflow.sdk import task"),
            helpers=(_AIRFLOW_DBT_HELPER,),
            lines=(f"{variable} = _dbt_build_task({arguments})",),
        )
    return RenderedTask(
        imports=("import importlib.util", "from airflow.sdk import task"),
        helpers=(_AIRFLOW_HELPER,),
        lines=(f"{variable} = _build_task({', '.join(_python_arguments(task, call))})",),
    )


def _plain_function(task: BuildTask, variable: str) -> RenderedTask:
    call = task.call
    if isinstance(call, DbtCall):
        return RenderedTask(
            imports=("import os", "import subprocess"),
            helpers=(_FUNCTION_DBT_HELPER,),
            lines=(f"{variable} = _dbt_build_function({', '.join(_dbt_arguments(call))})",),
        )
    return RenderedTask(
        imports=("import importlib.util",),
        helpers=(_FUNCTION_HELPER,),
        lines=(f"{variable} = _build_function({', '.join(_python_arguments(task, call))})",),
    )
