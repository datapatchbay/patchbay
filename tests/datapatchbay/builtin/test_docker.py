from dataclasses import replace
from pathlib import Path

from container_helpers import render, table_of

from datapatchbay.builtin.docker import DockerRuntime


def test_docker_runs_a_container_from_the_resolved_image(lab_repo: Path):
    table = replace(table_of(lab_repo), image="registry/lab:1")
    rendered = render(DockerRuntime(), table)
    code = "\n".join(rendered.lines)
    assert rendered.imports == ("from airflow.providers.docker.operators.docker import DockerOperator",)
    assert code.startswith("build = DockerOperator(")
    assert 'task_id="build_ingested_orders"' in code
    assert 'image="registry/lab:1"' in code
    assert 'entrypoint=["python"]' in code
