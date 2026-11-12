"""The `worker` runtime: the entrypoint is called on the orchestrator's worker, in the worker's environment.

For `airflow` the build is rendered as an Airflow task. For the orchestrators whose generated file is plain Python
(`FUNCTION_ORCHESTRATORS`) it is rendered as a function with no arguments, which the orchestrator calls when the
build has to run.
"""

from datapatchbay.literals import python_literal
from datapatchbay.plugins import BuildTask, DbtCall, PythonCall, RenderedTask, UnsupportedCombinationError

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

FUNCTION_ORCHESTRATORS = frozenset({"dagster", "local"})
"""The orchestrators that get the build as a function with no arguments instead of an Airflow task."""

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
    runs_dbt = True

    def render_build_task(self, task: BuildTask, *, orchestrator: str, variable: str) -> RenderedTask:
        """Render a task that calls the function, or runs `dbt build` on the worker for a `DbtCall`.

        The module is imported when the build runs, not while the orchestrator loads the file; `dbt` is run as a
        command of the worker.

        For `airflow`, `variable` is assigned an Airflow task. For an orchestrator in `FUNCTION_ORCHESTRATORS` it is
        assigned a function with no arguments that runs the build and raises when the build fails. In both cases the
        generated file must define `DATAPRODUCT_DIR`, the data product folder.

        Raises:
            UnsupportedCombinationError: If the orchestrator is neither `airflow` nor in `FUNCTION_ORCHESTRATORS`.
            ValueError: If a param is not a plain YAML value.
        """
        if orchestrator == "airflow":
            return _airflow_task(task, variable)
        if orchestrator in FUNCTION_ORCHESTRATORS:
            return _function(task, variable)
        raise UnsupportedCombinationError(f"the worker runtime cannot render tasks for orchestrator '{orchestrator}'")


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


def _function(task: BuildTask, variable: str) -> RenderedTask:
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
