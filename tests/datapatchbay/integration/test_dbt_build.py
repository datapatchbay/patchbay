"""`dbt build` on the generated dbt tests, against a real Postgres. An integration test (ADR-0020)."""

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pytest
from dbt_helpers import DP, MODEL, TABLE, TABLE_YAML, write
from plugin_fakes import FakeOrchestrator, register

from datapatchbay.generate import generate_repo

NAME = "agg_order_turnaround__turnaround"
REF = f"{{{{ ref('{NAME}') }}}}"


@pytest.fixture
def repo(jaffle_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    register(monkeypatch, "orchestrator", "fake", FakeOrchestrator)
    (jaffle_repo / "datapatchbay.yaml").write_text("schema_version: 1\norchestrator: fake\n")
    write(jaffle_repo, "dbt_project.yml", "name: jaffle_shop\nversion: '1.0.0'\nprofile: jaffle_shop\n")
    product = jaffle_repo / DP / "dataproduct.yaml"
    product.write_text(product.read_text() + "executor: dbt\n")
    write(jaffle_repo, TABLE, TABLE_YAML)
    write(jaffle_repo, MODEL, "select 1 as days\n")
    return jaffle_repo


def with_rules(repo: Path, rules: str) -> None:
    write(repo, TABLE, TABLE_YAML + "rules:\n" + rules)


def test_dbt_build_runs_the_generated_tests_against_postgres(repo: Path, tmp_path: Path):
    dbt = shutil.which("dbt")
    url = os.environ.get("DPB_TEST_POSTGRES_URL")
    if url is None:
        pytest.fail("DPB_TEST_POSTGRES_URL is not set; run the integration tests with scripts/integration-tests")
    if dbt is None:
        pytest.fail(
            "dbt is not installed (dependency group `dbt`); run the integration tests with scripts/integration-tests"
        )
    parsed = urlparse(url)
    write(repo, MODEL, "select 1::numeric as days union all select 1::numeric\n")  # the key `days` repeats
    with_rules(
        repo,
        "  - {rule: primary_key, columns: [days]}\n"  # fails
        "  - {rule: row_count, min: 1}\n"  # passes
        f"  - rule: sql\n    sql: select * from {REF} where days < 0;\n",  # passes
    )
    generate_repo(repo)
    profiles = tmp_path / "profiles"
    write(
        profiles,
        "profiles.yml",
        "jaffle_shop:\n  target: dev\n  outputs:\n    dev:\n"
        f"      {{type: postgres, host: '{parsed.hostname}', port: {parsed.port or 5432}, user: '{parsed.username}', "
        f"password: '{parsed.password}', dbname: '{parsed.path.lstrip('/')}', "
        f"schema: dpb_test_{uuid.uuid4().hex[:8]}, threads: 1}}\n",
    )
    build = subprocess.run(
        [dbt, "build", "--project-dir", str(repo), "--profiles-dir", str(profiles)],
        capture_output=True,
        text=True,
        check=False,
    )  # the failing key makes the exit code non-zero; the statuses below say what ran
    results = json.loads((repo / "target" / "run_results.json").read_text())["results"]
    statuses = {r["unique_id"].split(".")[2]: r["status"] for r in results}
    assert statuses == {
        NAME: "success",
        f"{NAME}__primary_key": "fail",
        f"{NAME}__row_count": "pass",
        f"{NAME}__sql": "pass",
    }, build.stdout + build.stderr
