import datetime
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from container_helpers import render, table_of

from datapatchbay.integrations._container.container import ENTRYPOINT_LOADER
from datapatchbay.integrations.docker.runtime import DockerRuntime
from datapatchbay.integrations.kubernetes.runtime import KubernetesRuntime
from datapatchbay.plugins import UnsupportedCombinationError


@pytest.mark.parametrize("runtime", [DockerRuntime(), KubernetesRuntime()])
def test_a_container_runtime_refuses_a_table_without_an_image(jaffle_repo: Path, runtime: DockerRuntime):
    with pytest.raises(UnsupportedCombinationError, match="table 'ingested_orders' has no image"):
        render(runtime, table_of(jaffle_repo))


@pytest.mark.parametrize(
    ("runtime", "key"), [(DockerRuntime(), "image"), (DockerRuntime(), "command"), (KubernetesRuntime(), "arguments")]
)
def test_the_container_setting_cannot_replace_what_dpb_sets(jaffle_repo: Path, runtime: DockerRuntime, key: str):
    table = replace(table_of(jaffle_repo), image="x:1", container={key: "y"})
    with pytest.raises(UnsupportedCombinationError, match=f"'{key}'"):
        render(runtime, table)


def test_the_container_setting_is_handed_over_as_written(jaffle_repo: Path):
    container = {"environment": {"PGHOST": "db", "PGPASSWORD": "{{ conn.warehouse.password }}"}, "mem_limit": "1g"}
    table = replace(table_of(jaffle_repo), image="x:1", container=container)
    code = "\n".join(render(DockerRuntime(), table).lines)
    assert 'environment={"PGHOST": "db", "PGPASSWORD": "{{ conn.warehouse.password }}"},' in code
    assert 'mem_limit="1g",' in code


def test_a_container_setting_that_is_not_a_keyword_is_refused(jaffle_repo: Path):
    table = replace(table_of(jaffle_repo), image="x:1", container={"not a name": 1})
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


def test_the_rendered_task_carries_the_file_function_and_params_as_arguments(jaffle_repo: Path):
    table = replace(table_of(jaffle_repo), image="x:1")
    code = "\n".join(render(DockerRuntime(), table).lines)
    assert '"src/ingested.py", "build", "{\\"limit\\":100}"' in code


def test_a_param_that_is_not_a_plain_value_is_refused(jaffle_repo: Path):
    table = replace(table_of(jaffle_repo), image="x:1", params={"day": datetime.date(2025, 1, 1)})
    with pytest.raises(ValueError, match="not a plain value"):
        render(DockerRuntime(), table)
