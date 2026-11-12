"""The `docker` runtime: a container from the resolved image, run on the worker host by Airflow's DockerOperator."""

from datapatchbay.builtin.container import image_of, loader_arguments, operator_call
from datapatchbay.plugins import BuildTask, RenderedTask, UnsupportedCombinationError


class DockerRuntime:
    """Run the entrypoint in a Docker container (ADR-0016)."""

    needs_image = True

    def render_build_task(self, task: BuildTask, *, orchestrator: str, variable: str) -> RenderedTask:
        """Render a `DockerOperator` task; the table's `container` setting is added to it as written.

        Raises:
            UnsupportedCombinationError: If the orchestrator is not `airflow`, the table has no image, or
                `container` names an argument that dpb sets.
            ValueError: If a param or a `container` value is not a plain YAML value.
        """
        if orchestrator != "airflow":
            raise UnsupportedCombinationError(
                f"the docker runtime cannot render tasks for orchestrator '{orchestrator}'"
            )
        command = loader_arguments(task, "docker")  # first, so a dbt call is refused before a missing image
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
