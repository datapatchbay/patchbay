import datetime
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from datapatchbay.builtin.container import ENTRYPOINT_LOADER
from datapatchbay.builtin.docker import DockerRuntime
from datapatchbay.builtin.kubernetes import KubernetesRuntime
from datapatchbay.builtin.python_executor import PythonExecutor
from datapatchbay.generate import generate_repo
from datapatchbay.loading import load_repo
from datapatchbay.planning import plan_dataproducts
from datapatchbay.plugins import BuildTask, RenderedTask, TablePlan, UnsupportedCombinationError
from datapatchbay.settings import load_settings
from datapatchbay.validation import validate_repo

ORDERS = "dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/orders.yaml"
INGESTED = "dataproducts/sa_ilab_orders/inputs/sa_ilab_orders_private/ingested.yaml"


def table_of(root: Path, name: str = "ingested_orders") -> TablePlan:
    repo, problems = load_repo(root)
    assert problems == []
    plans = plan_dataproducts(repo, load_settings(root))
    return next(t for plan in plans for t in plan.tables if t.name == name)


def render(runtime: DockerRuntime | KubernetesRuntime, table: TablePlan) -> RenderedTask:
    task = BuildTask(f"build_{table.name}", table, PythonExecutor().call(table))
    return runtime.render_build_task(task, orchestrator="airflow", variable="build")


def test_docker_runs_a_container_from_the_resolved_image(lab_repo: Path):
    table = replace(table_of(lab_repo), image="registry/lab:1")
    rendered = render(DockerRuntime(), table)
    code = "\n".join(rendered.lines)
    assert rendered.imports == ("from airflow.providers.docker.operators.docker import DockerOperator",)
    assert code.startswith("build = DockerOperator(")
    assert 'task_id="build_ingested_orders"' in code
    assert 'image="registry/lab:1"' in code
    assert 'entrypoint=["python"]' in code


def test_kubernetes_runs_a_pod_from_the_resolved_image_with_a_valid_pod_name(lab_repo: Path):
    table = replace(table_of(lab_repo), image="registry/lab:1")
    rendered = render(KubernetesRuntime(), table)
    code = "\n".join(rendered.lines)
    assert rendered.imports == ("from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator",)
    assert code.startswith("build = KubernetesPodOperator(")
    assert 'image="registry/lab:1"' in code
    assert 'name="sa-ilab-orders-ingested-orders"' in code
    assert 'cmds=["python"]' in code


@pytest.mark.parametrize("runtime", [DockerRuntime(), KubernetesRuntime()])
def test_a_container_runtime_refuses_a_table_without_an_image(lab_repo: Path, runtime: DockerRuntime):
    with pytest.raises(UnsupportedCombinationError, match="table 'ingested_orders' has no image"):
        render(runtime, table_of(lab_repo))


@pytest.mark.parametrize(
    ("runtime", "key"), [(DockerRuntime(), "image"), (DockerRuntime(), "command"), (KubernetesRuntime(), "arguments")]
)
def test_the_container_setting_cannot_replace_what_dpb_sets(lab_repo: Path, runtime: DockerRuntime, key: str):
    table = replace(table_of(lab_repo), image="x:1", container={key: "y"})
    with pytest.raises(UnsupportedCombinationError, match=f"'{key}'"):
        render(runtime, table)


def test_the_container_setting_is_handed_over_as_written(lab_repo: Path):
    container = {"environment": {"PGHOST": "db", "PGPASSWORD": "{{ conn.warehouse.password }}"}, "mem_limit": "1g"}
    table = replace(table_of(lab_repo), image="x:1", container=container)
    code = "\n".join(render(DockerRuntime(), table).lines)
    assert 'environment={"PGHOST": "db", "PGPASSWORD": "{{ conn.warehouse.password }}"},' in code
    assert 'mem_limit="1g",' in code


def test_a_container_setting_that_is_not_a_keyword_is_refused(lab_repo: Path):
    table = replace(table_of(lab_repo), image="x:1", container={"not a name": 1})
    with pytest.raises(UnsupportedCombinationError, match="'not a name'"):
        render(DockerRuntime(), table)


def test_the_entrypoint_and_its_params_reach_the_function_in_the_container(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/orders.py").write_text(
        "import json\n\ndef build(mode, limit):\n    print(json.dumps({'mode': mode, 'limit': limit}))\n"
    )
    params = json.dumps({"mode": "full", "limit": 3})
    done = subprocess.run(
        [sys.executable, "-c", ENTRYPOINT_LOADER, "src/orders.py", "build", params],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(done.stdout) == {"mode": "full", "limit": 3}


def test_the_rendered_task_carries_the_file_function_and_params_as_arguments(lab_repo: Path):
    table = replace(table_of(lab_repo), image="x:1")
    code = "\n".join(render(DockerRuntime(), table).lines)
    assert '"src/ingested.py", "build", "{\\"limit\\":100}"' in code


def test_a_param_that_is_not_a_plain_value_is_refused(lab_repo: Path):
    table = replace(table_of(lab_repo), image="x:1", params={"day": datetime.date(2025, 1, 1)})
    with pytest.raises(ValueError, match="not a plain value"):
        render(DockerRuntime(), table)


def test_docker_and_kubernetes_tables_sit_in_one_dag_with_other_runtimes(lab_repo: Path):
    ingested = lab_repo / INGESTED
    ingested.write_text(ingested.read_text().replace("build:\n", "build:\n  runtime: docker\n  image: lab:1\n"))
    orders = lab_repo / ORDERS
    orders.write_text(
        orders.read_text().replace(
            "build:\n", "build:\n  runtime: kubernetes\n  image: lab:2\n  container: {namespace: data}\n"
        )
    )
    generate_repo(lab_repo)
    dag = (lab_repo / "generated/sa_ilab_orders.py").read_text()
    assert "build_ingested_orders = DockerOperator(" in dag
    assert "build_orders = KubernetesPodOperator(" in dag
    assert 'namespace="data"' in dag
    assert "build_ingested_orders >> build_orders" in dag


def test_validate_fails_a_container_runtime_without_an_image(lab_repo: Path):
    path = lab_repo / INGESTED
    path.write_text(path.read_text().replace("build:\n", "build:\n  runtime: docker\n"))
    assert [p.render() for p in validate_repo(lab_repo).problems] == [
        f"{INGESTED}:7: runtime 'docker' needs an image, but none is set "
        "(data product 'sa_ilab_orders', table 'ingested_orders'); set `image` at the root, data product, port or table"
    ]


def test_validate_accepts_an_image_set_at_any_level(lab_repo: Path):
    port = lab_repo / "dataproducts/sa_ilab_orders/inputs/sa_ilab_orders_private/port.yaml"
    port.write_text(port.read_text() + "image: lab:1\n")
    path = lab_repo / INGESTED
    path.write_text(path.read_text().replace("build:\n", "build:\n  runtime: docker\n"))
    assert validate_repo(lab_repo).problems == []
