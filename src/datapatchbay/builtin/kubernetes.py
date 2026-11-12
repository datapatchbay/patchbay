"""The `kubernetes` runtime: a pod from the resolved image, run by Airflow's KubernetesPodOperator."""

import re

from datapatchbay.builtin.container import image_of, loader_arguments, operator_call
from datapatchbay.plugins import BuildTask, RenderedTask, UnsupportedCombinationError

_POD_NAME_LENGTH = 40
"""Airflow appends a random suffix of 9 characters to the name, and a pod name is at most 63."""


def pod_name(dataproduct: str, table: str) -> str:
    """Return a DNS-1123 label for the pod of a table: lower case letters, digits and dashes."""
    label = re.sub(r"[^a-z0-9]+", "-", f"{dataproduct}-{table}".lower()).strip("-")
    return label[:_POD_NAME_LENGTH].strip("-") or "build"


class KubernetesRuntime:
    """Run the entrypoint in a Kubernetes pod (ADR-0016)."""

    needs_image = True
    runs_dbt = False

    def render_build_task(self, task: BuildTask, *, orchestrator: str, variable: str) -> RenderedTask:
        """Render a `KubernetesPodOperator` task; the table's `container` setting is added to it as written.

        Raises:
            UnsupportedCombinationError: If the orchestrator is not `airflow`, the table has no image, or
                `container` names an argument that dpb sets.
            ValueError: If a param or a `container` value is not a plain YAML value.
        """
        if orchestrator != "airflow":
            raise UnsupportedCombinationError(
                f"the kubernetes runtime cannot render tasks for orchestrator '{orchestrator}'"
            )
        table = task.table
        arguments = loader_arguments(task, "kubernetes")  # first, so a dbt call is refused before a missing image
        set_by_dpb = {
            "task_id": task.task_id,
            "name": pod_name(table.dataproduct, table.name),
            "image": image_of(task, "kubernetes"),
            "cmds": ["python"],
            "arguments": arguments,
        }
        return RenderedTask(
            imports=("from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator",),
            lines=operator_call(variable, "KubernetesPodOperator", set_by_dpb, table.container),
        )
