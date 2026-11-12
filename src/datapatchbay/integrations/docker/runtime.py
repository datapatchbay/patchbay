"""The `docker` runtime: a container from the resolved image, run on the worker host by Airflow's DockerOperator."""

from datapatchbay.integrations._container.container import image_of, loader_arguments, operator_call
from datapatchbay.plugins import BuildTask, PythonCall, RenderedTask, RenderKind


class DockerRuntime:
    """Run the entrypoint in a Docker container (ADR-0016)."""

    needs_image = True
    call_types: tuple[type, ...] = (PythonCall,)
    render_kinds: frozenset[RenderKind] = frozenset({"task"})

    def render_build_task(self, task: BuildTask, *, kind: RenderKind, variable: str) -> RenderedTask:
        """Render a `DockerOperator` task; the table's `container` setting is added to it as written.

        Raises:
            UnsupportedCombinationError: If the table has no image, or
                `container` names an argument that dpb sets.
            ValueError: If a param or a `container` value is not a plain YAML value.
        """
        command = loader_arguments(task, "docker")  # first, so another call is refused before a missing image
        set_by_dpb = {
            "task_id": task.task_id,
            "image": image_of(task, "docker"),
            "entrypoint": ["python"],
            "command": command,
        }
        return RenderedTask(
            imports=("from airflow.providers.docker.operators.docker import DockerOperator",),
            lines=operator_call(variable, "DockerOperator", set_by_dpb, task.table.container),
        )
