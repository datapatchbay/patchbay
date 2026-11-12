"""The `worker` runtime: the entrypoint is called on the orchestrator's worker, in the worker's environment."""

from datapatchbay.literals import python_literal
from datapatchbay.plugins import BuildTask, RenderedTask, UnsupportedCombinationError

_AIRFLOW_HELPER = '''\
def _build_task(task_id, path, function, params):
    """Create a task that loads a file of the data product and calls a function in it."""

    @task(task_id=task_id)
    def build():
        spec = importlib.util.spec_from_file_location(f"patchbay_{task_id}", DATAPRODUCT_DIR / path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        getattr(module, function)(**params)

    return build()'''


class WorkerRuntime:
    """Call the entrypoint inside an Airflow task, so it runs on the worker."""

    def render_build_task(self, task: BuildTask, *, orchestrator: str, variable: str) -> RenderedTask:
        """Render a task that calls the function; the module is imported inside the task, not while Airflow parses.

        For the `airflow` orchestrator the generated file must define `DATAPRODUCT_DIR`, the data product folder.

        Raises:
            UnsupportedCombinationError: If the orchestrator is not `airflow`.
            ValueError: If a param is not a plain YAML value.
        """
        if orchestrator != "airflow":
            raise UnsupportedCombinationError(
                f"the worker runtime cannot render tasks for orchestrator '{orchestrator}'"
            )
        call = task.call
        arguments = ", ".join(
            [
                python_literal(task.task_id),
                python_literal(call.file.as_posix()),
                python_literal(call.function),
                python_literal(call.params),
            ]
        )
        return RenderedTask(
            imports=("import importlib.util", "from airflow.sdk import task"),
            helpers=(_AIRFLOW_HELPER,),
            lines=(f"{variable} = _build_task({arguments})",),
        )
