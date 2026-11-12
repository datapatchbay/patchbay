from dataclasses import replace
from pathlib import Path

from container_helpers import render, table_of

from datapatchbay.integrations.kubernetes.runtime import KubernetesRuntime


def test_kubernetes_runs_a_pod_from_the_resolved_image_with_a_valid_pod_name(jaffle_repo: Path):
    table = replace(table_of(jaffle_repo), image="registry/jaffle-shop:1")
    rendered = render(KubernetesRuntime(), table)
    code = "\n".join(rendered.lines)
    assert rendered.imports == ("from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator",)
    assert code.startswith("build = KubernetesPodOperator(")
    assert 'image="registry/jaffle-shop:1"' in code
    assert 'name="sa-jaffle-orders-ingested-orders"' in code
    assert 'cmds=["python"]' in code
