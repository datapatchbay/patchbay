import ast
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from local_expected import SA_SHOP_ORDERS
from local_support import AGG, SA, generate, query, run_script, write_repo
from plan_helpers import plan_all

from datapatchbay import registry
from datapatchbay.builtin.dbt_executor import DbtExecutor
from datapatchbay.builtin.docker import DockerRuntime
from datapatchbay.builtin.duckdb import DuckDbWarehouse
from datapatchbay.builtin.kubernetes import KubernetesRuntime
from datapatchbay.builtin.local import LocalOrchestrator, connection_variable
from datapatchbay.builtin.python_executor import PythonExecutor
from datapatchbay.builtin.worker import WorkerRuntime
from datapatchbay.generate import generate_repo
from datapatchbay.loading import load_repo
from datapatchbay.plugins import DataProductPlan, GenerationContext, UnsupportedCombinationError

# --- the generated text ---


def test_the_local_orchestrator_is_registered_through_its_entry_point():
    assert isinstance(registry.load_plugin("orchestrator", "local"), LocalOrchestrator)
    assert "local" in registry.plugin_names("orchestrator")


def test_generate_writes_one_complete_script_per_data_product_next_to_the_airflow_dag_files(tmp_path: Path):
    root = write_repo(tmp_path)
    result = generate_repo(root)
    assert result.report.ok
    assert [str(path) for path in result.files] == ["agg_order_totals.py", "sa_shop_orders.py"]
    assert (root / "generated/sa_shop_orders.py").read_text() == SA_SHOP_ORDERS


def test_the_script_is_the_same_every_time_it_is_generated(tmp_path: Path):
    root = write_repo(tmp_path)
    first = (generate(root) / "agg_order_totals.py").read_text()
    second = (generate(root) / "agg_order_totals.py").read_text()
    assert first == second


def test_the_script_holds_plain_constants_that_another_script_can_read_without_importing_it(tmp_path: Path):
    script = generate(write_repo(tmp_path)) / "agg_order_totals.py"
    names = {"ORCHESTRATOR", "DATAPRODUCT", "READS", "OUTPUTS", "CONNECTION_VARIABLE"}
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in ast.parse(script.read_text()).body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in names
    }
    assert constants == {
        "ORCHESTRATOR": "local",
        "DATAPRODUCT": "agg_order_totals",
        "READS": ("sa_shop_orders",),
        "OUTPUTS": ("agg_order_totals",),
        "CONNECTION_VARIABLE": "DPB_CONNECTION_WAREHOUSE",
    }


def test_importing_the_script_does_nothing_and_needs_neither_datapatchbay_nor_a_connection(tmp_path: Path):
    script = generate(write_repo(tmp_path)) / "sa_shop_orders.py"
    code = (
        "import runpy, sys\n"
        f"namespace = runpy.run_path({str(script)!r}, run_name='imported')\n"
        "assert not [name for name in sys.modules if name.split('.')[0] in ('datapatchbay', 'duckdb', 'psycopg')]\n"
        "print(namespace['ORCHESTRATOR'], namespace['DATAPRODUCT_DIR'].name)\n"
    )
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["local", "sa_shop_orders"]
    assert not (tmp_path / "shop.duckdb").exists()


def test_the_script_names_the_schedule_of_each_source_input_port_in_a_comment(tmp_path: Path):
    generated = generate(write_repo(tmp_path))
    assert "#   0 5 * * *  sa_shop_orders_private\n" in (generated / "sa_shop_orders.py").read_text()
    assert "does not schedule itself" not in (generated / "agg_order_totals.py").read_text()


# --- running the scripts ---


def test_running_a_script_builds_the_tables_and_applies_the_output_port_views(tmp_path: Path):
    generated = generate(write_repo(tmp_path))
    database = tmp_path / "shop.duckdb"

    done = run_script(generated / "sa_shop_orders.py", database=database)

    assert done.returncode == 0, done.stderr
    assert query(database, "SELECT order_id FROM sa_shop_orders_private.orders ORDER BY 1") == [(1,), (2,), (3,)]
    assert query(database, "SELECT order_id FROM sa_shop_orders.orders ORDER BY 1") == [(1,), (2,), (3,)]
    steps = [line.split(" INFO ")[1] for line in done.stderr.splitlines() if " INFO " in line]
    assert steps == [
        "sa_shop_orders: build_raw_orders",
        "sa_shop_orders: build_orders",
        "sa_shop_orders: audit_orders",
        "sa_shop_orders: apply_access",
    ]


def test_running_a_script_twice_builds_the_data_product_again(tmp_path: Path):
    script = generate(write_repo(tmp_path)) / "sa_shop_orders.py"
    database = tmp_path / "shop.duckdb"
    assert run_script(script, database=database).returncode == 0
    assert run_script(script, database=database).returncode == 0
    assert query(database, "SELECT count(*) FROM sa_shop_orders.orders") == [(3,)]


def test_a_broken_error_rule_fails_the_script_and_the_apply_step_does_not_run(tmp_path: Path):
    root = write_repo(
        tmp_path,
        **{
            f"{SA}/src/orders.py": (
                "import os\n\nimport duckdb\n\n\ndef build():\n"
                "    connection = duckdb.connect(os.environ['SHOP_DB'])\n"
                "    connection.execute(\n"
                "        'CREATE TABLE sa_shop_orders_private.orders AS SELECT NULL::INTEGER AS order_id'\n"
                "    )\n"
                "    connection.close()\n"
            )
        },
    )
    database = tmp_path / "shop.duckdb"

    done = run_script(generate(root) / "sa_shop_orders.py", database=database)

    assert done.returncode != 0
    assert "quality rule 'not_null' is broken on table 'orders', column 'order_id': 1 violation(s)" in done.stderr
    assert query(database, "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'sa_shop_orders'") == [
        (0,)
    ]


def test_a_broken_warning_rule_is_logged_and_the_script_goes_on(tmp_path: Path):
    root = write_repo(
        tmp_path,
        **{
            f"{SA}/outputs/sa_shop_orders/orders.yaml": (
                "schema_version: 1\nname: orders\ncolumns:\n  - name: order_id\n    type: integer\n"
                "    rules: [{rule: accepted_values, values: [1, 2], severity: warning}]\n"
                "build:\n  entrypoint: src/orders.py:build\n  needs: [raw_orders]\n"
            )
        },
    )
    database = tmp_path / "shop.duckdb"

    done = run_script(generate(root) / "sa_shop_orders.py", database=database)

    assert done.returncode == 0, done.stderr
    assert "WARNING quality rule 'accepted_values' is broken on table 'orders', column 'order_id'" in done.stderr
    assert query(database, "SELECT count(*) FROM sa_shop_orders.orders") == [(3,)]


def test_a_failing_build_stops_the_script_before_the_next_step(tmp_path: Path):
    root = write_repo(tmp_path, **{f"{SA}/src/raw.py": "def build():\n    raise RuntimeError('source is down')\n"})
    database = tmp_path / "shop.duckdb"

    done = run_script(generate(root) / "sa_shop_orders.py", database=database)

    assert done.returncode != 0
    assert "source is down" in done.stderr
    assert "build_orders" not in done.stderr
    assert not database.exists()


# --- --upstream ---


def test_upstream_runs_the_data_products_it_reads_first_and_then_itself(tmp_path: Path):
    generated = generate(write_repo(tmp_path))
    database = tmp_path / "shop.duckdb"

    alone = run_script(generated / "agg_order_totals.py", database=database)
    assert alone.returncode != 0  # the output port of sa_shop_orders is not there yet

    done = run_script(generated / "agg_order_totals.py", "--upstream", database=database)

    assert done.returncode == 0, done.stderr
    assert query(database, "SELECT n FROM agg_order_totals.totals") == [(3,)]
    steps = [line.split(" INFO ")[1] for line in done.stderr.splitlines() if " INFO " in line]
    assert steps == [
        "agg_order_totals: running upstream data product sa_shop_orders",
        "sa_shop_orders: build_raw_orders",
        "sa_shop_orders: build_orders",
        "sa_shop_orders: audit_orders",
        "sa_shop_orders: apply_access",
        "agg_order_totals: build_totals",
        "agg_order_totals: apply_access",
    ]


def stub(folder: Path, name: str, *, reads=(), outputs=(), orchestrator: str = "local", exit_code: int = 0) -> None:
    """A sibling script that only records that it ran, in the file named by `RUN_LOG`."""
    (folder / f"{name}.py").write_text(
        f"ORCHESTRATOR = {orchestrator!r}\nREADS = {tuple(reads)!r}\nOUTPUTS = {tuple(outputs)!r}\n\n\n"
        'if __name__ == "__main__":\n'
        "    import os\n    import sys\n\n"
        f'    with open(os.environ["RUN_LOG"], "a") as log:\n        log.write("{name}\\n")\n'
        f"    sys.exit({exit_code})\n"
    )


TOTALS_FROM_NOTHING = (
    "import os\n\nimport duckdb\n\n\ndef build():\n"
    "    connection = duckdb.connect(os.environ['SHOP_DB'])\n"
    "    connection.execute('CREATE SCHEMA IF NOT EXISTS agg_order_totals_private')\n"
    "    connection.execute('CREATE TABLE agg_order_totals_private.totals AS SELECT 7::INTEGER AS n')\n"
    "    connection.close()\n"
)


def test_upstream_runs_every_data_product_read_directly_or_indirectly_once_in_dependency_order(tmp_path: Path):
    generated = generate(write_repo(tmp_path, **{f"{AGG}/src/totals.py": TOTALS_FROM_NOTHING}))
    (generated / "sa_shop_orders.py").unlink()
    stub(generated, "stub_a", outputs=["pa"])
    stub(generated, "stub_b", reads=["pa"], outputs=["pb"])
    stub(generated, "stub_c", reads=["pa"], outputs=["pc"])
    stub(generated, "sa_shop_orders", reads=["pb", "pc"], outputs=["sa_shop_orders"])
    stub(generated, "unrelated", outputs=["pz"])
    log = tmp_path / "run.log"
    database = tmp_path / "shop.duckdb"

    done = run_script(
        generated / "agg_order_totals.py", "--upstream", database=database, extra_environment={"RUN_LOG": str(log)}
    )

    assert done.returncode == 0, done.stderr
    assert log.read_text().split() == ["stub_a", "stub_b", "stub_c", "sa_shop_orders"]
    assert query(database, "SELECT n FROM agg_order_totals.totals") == [(7,)]


def test_upstream_skips_with_a_warning_a_port_that_no_local_script_produces(tmp_path: Path):
    generated = generate(write_repo(tmp_path, **{f"{AGG}/src/totals.py": TOTALS_FROM_NOTHING}))
    (generated / "sa_shop_orders.py").unlink()
    stub(generated, "sa_shop_orders", reads=["pz"], outputs=["sa_shop_orders"])
    stub(generated, "on_airflow", outputs=["pz"], orchestrator="airflow")
    log = tmp_path / "run.log"

    done = run_script(
        generated / "agg_order_totals.py",
        "--upstream",
        database=tmp_path / "shop.duckdb",
        extra_environment={"RUN_LOG": str(log)},
    )

    assert done.returncode == 0, done.stderr
    assert "WARNING sa_shop_orders reads port 'pz', which no local data product here produces" in done.stderr
    assert log.read_text().split() == ["sa_shop_orders"]


def test_upstream_refuses_a_cycle_and_runs_nothing(tmp_path: Path):
    generated = generate(write_repo(tmp_path))
    (generated / "sa_shop_orders.py").unlink()
    stub(generated, "sa_shop_orders", reads=["pb"], outputs=["sa_shop_orders"])
    stub(generated, "stub_b", reads=["sa_shop_orders"], outputs=["pb"])
    log = tmp_path / "run.log"

    done = run_script(
        generated / "agg_order_totals.py",
        "--upstream",
        database=tmp_path / "shop.duckdb",
        extra_environment={"RUN_LOG": str(log)},
    )

    assert done.returncode != 0
    assert "read each other in a cycle: agg_order_totals -> sa_shop_orders -> stub_b -> sa_shop_orders" in done.stderr
    assert not log.exists()


def test_a_failing_upstream_data_product_stops_the_run_before_the_data_product_itself(tmp_path: Path):
    generated = generate(write_repo(tmp_path))
    (generated / "sa_shop_orders.py").unlink()
    stub(generated, "sa_shop_orders", outputs=["sa_shop_orders"], exit_code=3)
    database = tmp_path / "shop.duckdb"

    done = run_script(
        generated / "agg_order_totals.py",
        "--upstream",
        database=database,
        extra_environment={"RUN_LOG": str(tmp_path / "run.log")},
    )

    assert done.returncode != 0
    assert "build_totals" not in done.stderr
    assert not database.exists()


# --- the connection ---


@pytest.mark.parametrize(
    ("connection", "variable"),
    [
        ("warehouse", "DPB_CONNECTION_WAREHOUSE"),
        ("shop-db", "DPB_CONNECTION_SHOP_DB"),
        ("my.wh_1", "DPB_CONNECTION_MY_WH_1"),
    ],
)
def test_the_connection_setting_names_the_environment_variable_with_the_url(connection: str, variable: str):
    assert connection_variable(connection) == variable


def test_the_connection_setting_changes_the_variable_the_script_reads(tmp_path: Path):
    root = write_repo(
        tmp_path,
        **{
            "datapatchbay.yaml": "schema_version: 1\norchestrator: local\nwarehouse: duckdb\n"
            "runtime: worker\nconnection: shop-db\n"
        },
    )
    script = generate(root) / "sa_shop_orders.py"
    database = tmp_path / "shop.duckdb"

    done = run_script(script, database=database, variable="DPB_CONNECTION_SHOP_DB")
    assert done.returncode == 0, done.stderr
    assert query(database, "SELECT count(*) FROM sa_shop_orders.orders") == [(3,)]

    missing = run_script(script, database=tmp_path / "other.duckdb")
    assert missing.returncode != 0
    assert "environment variable DPB_CONNECTION_SHOP_DB is not set" in missing.stderr


def test_a_missing_connection_variable_is_named_with_the_supported_forms(tmp_path: Path):
    script = generate(write_repo(tmp_path)) / "sa_shop_orders.py"

    done = run_script(script, database=tmp_path / "shop.duckdb", without_connection=True)

    assert done.returncode != 0
    assert "environment variable DPB_CONNECTION_WAREHOUSE is not set" in done.stderr
    assert "duckdb:<path>" in done.stderr
    assert "postgresql://" in done.stderr


def test_an_unsupported_connection_url_is_refused_without_printing_it(tmp_path: Path):
    script = generate(write_repo(tmp_path)) / "sa_shop_orders.py"

    done = run_script(script, database=tmp_path / "shop.duckdb", url="mysql://user:hunter2@host/db")

    assert done.returncode != 0
    assert "environment variable DPB_CONNECTION_WAREHOUSE has an unsupported value (scheme 'mysql')" in done.stderr
    assert "duckdb:<path>" in done.stderr
    assert "hunter2" not in done.stderr


def test_a_duckdb_url_with_three_slashes_names_an_absolute_path(tmp_path: Path):
    script = generate(write_repo(tmp_path)) / "sa_shop_orders.py"
    database = tmp_path / "shop.duckdb"

    done = run_script(script, database=database, url=f"duckdb://{database}")

    assert done.returncode == 0, done.stderr
    assert query(database, "SELECT count(*) FROM sa_shop_orders.orders") == [(3,)]


FAKE_PSYCOPG = """\
import json
import subprocess
import os


class Connection:
    def execute(self, sql):
        with open(os.environ["FAKE_LOG"], "a") as log:
            log.write(json.dumps({"execute": sql[:30]}) + "\\n")
        return self

    def fetchone(self):
        return (0,)

    def close(self):
        with open(os.environ["FAKE_LOG"], "a") as log:
            log.write(json.dumps({"close": True}) + "\\n")


def connect(url, autocommit=False):
    with open(os.environ["FAKE_LOG"], "a") as log:
        log.write(json.dumps({"connect": url, "autocommit": autocommit}) + "\\n")
    return Connection()
"""


@pytest.mark.parametrize("url", ["postgresql://u:p@db.example.com/shop", "postgres://u:p@db.example.com/shop"])
def test_a_postgres_url_connects_with_psycopg_in_autocommit_mode_and_closes_each_connection(tmp_path: Path, url: str):
    script = generate(write_repo(tmp_path)) / "sa_shop_orders.py"
    drivers = tmp_path / "drivers"
    drivers.mkdir()
    (drivers / "psycopg.py").write_text(
        FAKE_PSYCOPG
    )  # a stand-in for the driver: the boundary datapatchbay does not own
    log = tmp_path / "psycopg.log"

    done = run_script(
        script,
        database=tmp_path / "shop.duckdb",
        url=url,
        extra_environment={"PYTHONPATH": str(drivers), "FAKE_LOG": str(log)},
    )

    assert done.returncode == 0, done.stderr
    events = [json.loads(line) for line in log.read_text().splitlines()]
    connects = [event for event in events if "connect" in event]
    assert connects == [{"connect": url, "autocommit": True}] * 2  # the audit step and the apply step
    assert [next(iter(event)) for event in events] == ["connect", "execute", "close", "connect", "execute", "close"]


# --- what the plugins can and cannot render ---


def test_the_docker_runtime_is_refused_when_generating(tmp_path: Path):
    root = write_repo(
        tmp_path,
        **{
            "datapatchbay.yaml": "schema_version: 1\norchestrator: local\nwarehouse: duckdb\nruntime: docker\n"
            "image: registry.example.com/shop:1\n"
        },
    )
    result = generate_repo(root)
    assert any(
        "the docker runtime cannot render tasks for orchestrator 'local'" in p.message for p in result.report.problems
    )
    assert not (root / "generated").exists()


def test_the_kubernetes_runtime_is_refused_when_generating(tmp_path: Path):
    root = write_repo(
        tmp_path,
        **{
            "datapatchbay.yaml": "schema_version: 1\norchestrator: local\nwarehouse: duckdb\nruntime: kubernetes\n"
            "image: registry.example.com/shop:1\n"
        },
    )
    result = generate_repo(root)
    assert any(
        "the kubernetes runtime cannot render tasks for orchestrator 'local'" in p.message
        for p in result.report.problems
    )


def plan_of(root: Path, folder: str) -> DataProductPlan:
    repo, problems = load_repo(root)
    assert problems == []
    plan = next(p for p in plan_all(repo, root) if p.folder == folder)
    return replace(plan, orchestrator="local")


def context_of(root: Path) -> GenerationContext:
    return GenerationContext(
        root=root,
        output_dir=root / "generated",
        executors={"python": PythonExecutor(), "dbt": DbtExecutor()},
        runtimes={"worker": WorkerRuntime(), "docker": DockerRuntime(), "kubernetes": KubernetesRuntime()},
        warehouse=DuckDbWarehouse(),
    )


def test_a_data_product_folder_that_is_not_a_valid_name_is_refused(tmp_path: Path):
    root = write_repo(tmp_path)
    plan = replace(plan_of(root, "sa_shop_orders"), folder="sa shop orders")
    with pytest.raises(UnsupportedCombinationError, match=r"data product 'sa shop orders' .* is not a valid name"):
        LocalOrchestrator().generate(plan, context_of(root))


def test_an_output_port_name_that_is_not_a_valid_name_is_refused(tmp_path: Path):
    root = write_repo(tmp_path)
    plan = replace(plan_of(root, "sa_shop_orders"), outputs=("sa/shop/orders",))
    with pytest.raises(UnsupportedCombinationError, match=r"port 'sa/shop/orders' .* is not a valid name"):
        LocalOrchestrator().generate(plan, context_of(root))


def test_a_connection_name_without_a_letter_or_digit_is_refused(tmp_path: Path):
    root = write_repo(tmp_path)
    plan = replace(plan_of(root, "sa_shop_orders"), connection="--")
    with pytest.raises(UnsupportedCombinationError, match="connection '--' has no letter or digit"):
        LocalOrchestrator().generate(plan, context_of(root))


def worker_plan(root: Path) -> DataProductPlan:
    """The data product that has a table built by dbt, with every table on the worker runtime."""
    plan = plan_of(root, "agg_weekly_orders")
    return replace(plan, tables=tuple(replace(t, runtime="worker", image=None, container={}) for t in plan.tables))


def test_the_dbt_build_runs_once_after_the_python_tables_and_before_the_warehouse_sql(jaffle_dbt_repo: Path):
    [file] = LocalOrchestrator().generate(worker_plan(jaffle_dbt_repo), context_of(jaffle_dbt_repo))

    run = file.content.split("def run():", 1)[1].split("\n\n\ndef ", 1)[0]
    assert [line.strip() for line in run.splitlines() if "_announce" in line] == [
        '_announce("build_weekly_raw")',
        '_announce("build_weekly")',
        '_announce("build_weekly_pod")',
        '_announce("build_dbt")',
    ]
    assert run.count("build_dbt()") == 1
    assert run.index("build_dbt()") < run.index('_sql_step("apply_access"')
    assert "#   30 6 * * 1  agg_weekly_orders_source\n" in file.content
    assert "def _dbt_build_function(" in file.content
    assert 'READS = ("sa_jaffle_orders",)' in file.content


def test_a_python_table_cannot_need_a_table_that_dbt_builds(jaffle_dbt_repo: Path):
    plan = worker_plan(jaffle_dbt_repo)
    tables = tuple(replace(t, needs=("weekly_summary",)) if t.name == "weekly_pod" else t for t in plan.tables)
    with pytest.raises(UnsupportedCombinationError, match="table 'weekly_pod' needs table 'weekly_summary', which dbt"):
        LocalOrchestrator().generate(replace(plan, tables=tables), context_of(jaffle_dbt_repo))


def test_tables_built_by_dbt_in_one_task_need_the_same_runtime(jaffle_dbt_repo: Path):
    plan = worker_plan(jaffle_dbt_repo)
    first = next(t for t in plan.tables if t.executor == "dbt")
    second = replace(first, name="other", runtime="docker")
    with pytest.raises(UnsupportedCombinationError, match="'weekly_summary' and 'other' are built by dbt in one task"):
        LocalOrchestrator().generate(replace(plan, tables=(*plan.tables, second)), context_of(jaffle_dbt_repo))
