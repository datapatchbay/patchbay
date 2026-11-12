import re
from dataclasses import replace
from pathlib import Path

import pytest
from plan_helpers import plan_all
from plugin_fakes import FakeWarehouse
from typer.testing import CliRunner

from datapatchbay.builtin.dagster import DagsterOrchestrator
from datapatchbay.builtin.dbt_executor import DbtExecutor
from datapatchbay.builtin.docker import DockerRuntime
from datapatchbay.builtin.duckdb import DuckDbWarehouse
from datapatchbay.builtin.kubernetes import KubernetesRuntime
from datapatchbay.builtin.python_executor import PythonExecutor
from datapatchbay.builtin.worker import WorkerRuntime
from datapatchbay.cli import app
from datapatchbay.generate import generate_repo
from datapatchbay.loading import load_repo
from datapatchbay.plugins import (
    DataProductPlan,
    GenerationContext,
    SourceSchedule,
    UnsupportedCombinationError,
    Warehouse,
)
from datapatchbay.validation import validate_repo

SNAPSHOT = Path(__file__).with_name("dagster_sa_jaffle_orders_snapshot.txt")
SETTINGS = "schema_version: 1\norchestrator: dagster\nwarehouse: duckdb\nruntime: worker\n"
CONTAINER_FILES = (
    "dataproducts/agg_weekly_orders/outputs/agg_weekly_orders/weekly_pod.yaml",
    "dataproducts/agg_weekly_orders/inputs/agg_weekly_orders_source/weekly_raw.yaml",
)


def use_dagster(root: Path) -> None:
    """Make the whole fixture repo run on Dagster, with the worker runtime that it supports."""
    (root / "datapatchbay.yaml").write_text(SETTINGS)
    for relative in CONTAINER_FILES:
        path = root / relative
        path.write_text(
            "".join(
                line
                for line in path.read_text().splitlines(keepends=True)
                if "runtime:" not in line and "image:" not in line
            )
        )


def plan_of(root: Path, folder: str) -> DataProductPlan:
    repo, problems = load_repo(root)
    assert problems == []
    plans = plan_all(repo, root)
    return replace(next(plan for plan in plans if plan.folder == folder), orchestrator="dagster")


def context_of(root: Path, warehouse: Warehouse | None = None) -> GenerationContext:
    return GenerationContext(
        root=root,
        output_dir=root / "generated",
        executors={"python": PythonExecutor(), "dbt": DbtExecutor()},
        runtimes={"worker": WorkerRuntime(), "docker": DockerRuntime(), "kubernetes": KubernetesRuntime()},
        warehouse=warehouse if warehouse is not None else DuckDbWarehouse(),
    )


def module_of(root: Path, plan: DataProductPlan, warehouse: Warehouse | None = None) -> str:
    [file] = DagsterOrchestrator().generate(plan, context_of(root, warehouse))
    assert file.path.as_posix() == f"{plan.folder}.py"
    return file.content


def generated(root: Path, folder: str) -> str:
    return module_of(root, plan_of(root, folder))


def test_the_module_of_a_data_product_is_written_whole(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    assert generated(jaffle_repo, "sa_jaffle_orders") == SNAPSHOT.read_text()


def test_generation_is_deterministic(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    assert generated(jaffle_repo, "sa_jaffle_orders") == generated(jaffle_repo, "sa_jaffle_orders")


def test_every_generated_module_compiles_and_imports_only_dagster_and_the_standard_library(jaffle_dbt_repo: Path):
    use_dagster(jaffle_dbt_repo)
    for folder in ("sa_jaffle_orders", "agg_order_turnaround", "agg_weekly_orders"):
        source = generated(jaffle_dbt_repo, folder)
        compile(source, f"{folder}.py", "exec")
        modules = {m.split(".")[0] for m in re.findall(r"^(?:import|from) (\S+)", source, flags=re.MULTILINE)}
        assert modules <= {"dagster", "importlib", "os", "pathlib", "subprocess"}


def test_the_module_defines_the_data_product_dir_like_the_airflow_dag_file(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    source = generated(jaffle_repo, "sa_jaffle_orders")
    assert (
        'DATAPRODUCT_DIR = (Path(__file__).resolve().parent / "../dataproducts/sa_jaffle_orders").resolve()' in source
    )


def test_a_reader_depends_on_the_port_it_reads_and_runs_when_it_is_materialized(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    source = generated(jaffle_repo, "agg_order_turnaround")
    assert 'key=["agg_order_turnaround", "turnaround"]' in source
    assert 'dg.AssetKey(["sa_jaffle_orders"])' in source
    sensor = '_read_sensor("agg_order_turnaround__on_sa_jaffle_orders", "sa_jaffle_orders", job)'
    assert f"agg_order_turnaround__on_sa_jaffle_orders = {sensor}" in source
    assert "ScheduleDefinition" not in source  # no source input port, so nothing to schedule


def test_a_table_without_needs_depends_on_the_read_ports_and_a_table_with_needs_on_its_tables(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    source = generated(jaffle_repo, "agg_weekly_orders")
    raw, weekly, pod = (
        re.search(rf'key=\["agg_weekly_orders", "{t}"\].*?\n\)', source, re.DOTALL)
        for t in ("weekly_raw", "weekly", "weekly_pod")
    )
    assert raw is not None
    assert weekly is not None
    assert pod is not None
    assert 'dg.AssetKey(["sa_jaffle_orders"])' in raw.group()
    assert 'dg.AssetKey(["agg_weekly_orders", "weekly_raw"])' in weekly.group()
    assert "sa_jaffle_orders" not in weekly.group()
    assert 'dg.AssetKey(["agg_weekly_orders", "weekly"])' in pod.group()


def test_the_dbt_tables_are_one_multi_asset_after_the_python_tables_nothing_needs(jaffle_dbt_repo: Path):
    use_dagster(jaffle_dbt_repo)
    source = generated(jaffle_dbt_repo, "agg_weekly_orders")
    [block] = re.findall(
        r'@dg\.multi_asset\(\n    name="agg_weekly_orders__build_dbt".*?\n\)\n(.*?)\n\n\n', source, re.DOTALL
    )
    assert block.startswith("def agg_weekly_orders__build_dbt():\n    build_dbt()\n    yield dg.MaterializeResult(")
    spec = re.search(r'name="agg_weekly_orders__build_dbt".*?\n\)\n', source, re.DOTALL)
    assert spec is not None
    assert 'dg.AssetKey(["agg_weekly_orders", "weekly_pod"])' in spec.group()
    assert 'dg.AssetKey(["agg_weekly_orders", "weekly_raw"])' not in spec.group()
    assert 'build_dbt = _dbt_build_function("../..", "~/.dbt", "dataproducts/agg_weekly_orders/models")' in source
    assert "agg_weekly_orders__build_dbt,\n" in source.split("defs = ", 1)[1]


def test_the_output_port_asset_depends_on_every_table_and_exists_without_apply_sql(jaffle_dbt_repo: Path):
    use_dagster(jaffle_dbt_repo)
    plan = plan_of(jaffle_dbt_repo, "agg_weekly_orders")
    source = module_of(jaffle_dbt_repo, plan, warehouse=NoApplyWarehouse())
    [port] = re.findall(r'name="agg_weekly_orders__output_ports".*?\n\)\ndef .*?\n\n\n', source, re.DOTALL)
    for table in ("weekly_raw", "weekly", "weekly_pod", "weekly_summary"):
        assert f'dg.AssetKey(["agg_weekly_orders", "{table}"])' in port
    assert "required_resource_keys" not in port
    assert "def agg_weekly_orders__output_ports():\n    yield dg.MaterializeResult" in port


class NoApplyWarehouse(FakeWarehouse):
    def apply_tasks(self, dataproduct: DataProductPlan) -> list:
        return []

    def audit_tasks(self, table) -> list:
        return []


def test_the_resource_is_required_only_where_sql_runs(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    source = generated(jaffle_repo, "sa_jaffle_orders")
    assert source.count("required_resource_keys") == 2  # the rule check and the output ports
    [ingested] = re.findall(
        r'key=\["sa_jaffle_orders", "ingested_orders"\].*?\n    return dg.MaterializeResult\(\)', source, re.DOTALL
    )
    assert "resource" not in ingested


def test_the_connection_setting_is_the_resource_key(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    (jaffle_repo / "datapatchbay.yaml").write_text(SETTINGS + "connection: dwh\n")
    source = generated(jaffle_repo, "sa_jaffle_orders")
    assert 'required_resource_keys={"dwh"}' in source
    assert '"dwh",\n    [' in source
    assert '"warehouse"' not in source


def test_each_rule_is_its_own_check_with_its_severity_and_a_name_unique_for_the_table(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    path = jaffle_repo / "dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/orders.yaml"
    path.write_text(
        "schema_version: 1\nname: orders\ncolumns:\n  - name: order_id\n    type: text\n"
        "    rules: [not_null, {rule: not_null, severity: warning}]\n"
        "  - name: status\n    type: text\n"
        "build:\n  entrypoint: src/orders.py:build\n"
        "rules:\n  - {rule: primary_key, columns: [order_id, status]}\n"
    )
    source = generated(jaffle_repo, "sa_jaffle_orders")
    names = re.findall(r'\{"name": "(\w+)", "rule": "(\w+)".*?"severity": "(\w+)"', source)
    assert names == [
        ("not_null_order_id", "not_null", "error"),
        ("not_null_order_id_2", "not_null", "warning"),
        ("primary_key_order_id_status", "primary_key", "error"),
    ]


def test_a_plain_sql_audit_is_a_blocking_check_and_the_apply_sql_runs_in_order(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    plan = plan_of(jaffle_repo, "sa_jaffle_orders")
    source = module_of(jaffle_repo, plan, warehouse=FakeWarehouse())
    assert (
        "audit_orders = _sql_check(\n"
        '    "sa_jaffle_orders__audit_orders",\n    "audit_orders",\n    ["sa_jaffle_orders", "orders"],\n'
        "    \"warehouse\",\n    \"SELECT 'it''s' FROM orders WHERE false\",\n)"
    ) in source
    assert "audit_ingested_orders = _sql_check(" in source
    assert '_execute(connection, "GRANT USAGE ON SCHEMA sa_jaffle_orders TO reader;")' in source
    assert "blocking=True" in source


def test_the_job_selects_the_group_and_the_schedule_runs_it_at_the_cron_in_utc(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    source = generated(jaffle_repo, "sa_jaffle_orders")
    assert (
        'job = dg.define_asset_job(\n    name="sa_jaffle_orders",\n'
        '    selection=dg.AssetSelection.groups("sa_jaffle_orders"),\n)'
    ) in source
    assert (
        "schedule = dg.ScheduleDefinition(\n"
        '    name="sa_jaffle_orders__schedule",\n    job=job,\n    cron_schedule="0 5 * * *",\n'
        '    execution_timezone="UTC",\n    default_status=dg.DefaultScheduleStatus.RUNNING,\n)'
    ) in source


def test_source_ports_with_different_crons_become_one_schedule_with_all_the_crons(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    plan = plan_of(jaffle_repo, "sa_jaffle_orders")
    schedules = (SourceSchedule("a", "30 6 * * 1"), SourceSchedule("b", "0 5 * * *"), SourceSchedule("c", "0 5 * * *"))
    source = module_of(jaffle_repo, replace(plan, source_schedules=schedules))
    assert 'cron_schedule=["0 5 * * *", "30 6 * * 1"],' in source
    assert source.count("ScheduleDefinition(") == 1


def test_a_data_product_with_neither_assets_nor_outputs_has_empty_definitions(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    plan = replace(plan_of(jaffle_repo, "sa_jaffle_orders"), tables=(), outputs=(), reads=())
    source = module_of(jaffle_repo, plan)
    assert source.endswith("defs = dg.Definitions()\n")
    compile(source, "empty.py", "exec")


def test_the_owner_is_metadata_and_not_the_owners_of_dagster(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    source = generated(jaffle_repo, "sa_jaffle_orders")
    assert 'metadata={"owner": "Jane Doe"}' in source
    assert "owners=" not in source


def test_names_are_unique_across_data_products(jaffle_dbt_repo: Path):
    use_dagster(jaffle_dbt_repo)
    names: dict[str, set[str]] = {}
    for folder in ("sa_jaffle_orders", "agg_order_turnaround", "agg_weekly_orders"):
        source = generated(jaffle_dbt_repo, folder)
        found = set(re.findall(r'^\s+name="(\w+)",', source, re.MULTILINE))
        found |= set(re.findall(r'(?:_audit_check|_sql_check|_read_sensor)\(\s*"(\w+)"', source))
        found |= set(re.findall(r"^def (\w+)\(", source, re.MULTILINE)) - {"_build_function"}
        found = {name for name in found if not name.startswith("_")}
        assert found
        assert all(name.startswith(folder) for name in found), found
        names[folder] = found
    assert names["sa_jaffle_orders"].isdisjoint(names["agg_order_turnaround"] | names["agg_weekly_orders"])
    assert names["agg_order_turnaround"].isdisjoint(names["agg_weekly_orders"])


@pytest.mark.parametrize("runtime", ["docker", "kubernetes"])
def test_container_runtimes_are_refused_for_dagster(jaffle_repo: Path, runtime: str):
    use_dagster(jaffle_repo)
    plan = plan_of(jaffle_repo, "sa_jaffle_orders")
    tables = tuple(replace(t, runtime=runtime) for t in plan.tables)
    with pytest.raises(
        UnsupportedCombinationError, match=f"the {runtime} runtime cannot render tasks for orchestrator 'dagster'"
    ):
        DagsterOrchestrator().generate(replace(plan, tables=tables), context_of(jaffle_repo))


def test_a_param_that_is_not_a_plain_value_is_refused_with_the_table(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    plan = plan_of(jaffle_repo, "sa_jaffle_orders")
    tables = tuple(replace(t, params={"day": object()}) if t.name == "orders" else t for t in plan.tables)
    with pytest.raises(UnsupportedCombinationError, match="table 'orders': "):
        DagsterOrchestrator().generate(replace(plan, tables=tables), context_of(jaffle_repo))


def test_a_python_table_cannot_need_a_table_that_dbt_builds(jaffle_dbt_repo: Path):
    use_dagster(jaffle_dbt_repo)
    plan = plan_of(jaffle_dbt_repo, "agg_weekly_orders")
    tables = tuple(replace(t, needs=("weekly_summary",)) if t.name == "weekly_pod" else t for t in plan.tables)
    with pytest.raises(UnsupportedCombinationError, match="table 'weekly_pod' needs table 'weekly_summary', which dbt"):
        DagsterOrchestrator().generate(replace(plan, tables=tables), context_of(jaffle_dbt_repo))


def test_tables_built_by_dbt_in_one_task_need_the_same_runtime(jaffle_dbt_repo: Path):
    use_dagster(jaffle_dbt_repo)
    plan = plan_of(jaffle_dbt_repo, "agg_weekly_orders")
    first = next(t for t in plan.tables if t.executor == "dbt")
    second = replace(first, name="other", runtime="docker")
    with pytest.raises(UnsupportedCombinationError, match="'weekly_summary' and 'other' are built by dbt in one task"):
        DagsterOrchestrator().generate(replace(plan, tables=(*plan.tables, second)), context_of(jaffle_dbt_repo))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda plan: replace(plan, folder="sa-jaffle"),
            r"data product 'sa-jaffle' \(folder name\) is not a valid Dagster name",
        ),
        (
            lambda plan: replace(plan, outputs=("sa.jaffle",)),
            r"port 'sa\.jaffle' \(asset key\) is not a valid Dagster name",
        ),
        (lambda plan: replace(plan, reads=("a b",)), r"port 'a b' \(asset key\) is not a valid Dagster name"),
        (
            lambda plan: replace(plan, tables=(replace(plan.tables[0], name="in/gested"), *plan.tables[1:])),
            r"table 'in/gested' \(asset key\) is not a valid Dagster name",
        ),
        (
            lambda plan: replace(plan, connection="my-dwh"),
            r"connection 'my-dwh' \(resource key\) is not a valid Dagster name",
        ),
    ],
    ids=["folder", "output port", "read port", "table", "connection"],
)
def test_a_name_that_dagster_does_not_accept_is_refused(jaffle_repo: Path, change, message: str):
    use_dagster(jaffle_repo)
    plan = change(plan_of(jaffle_repo, "sa_jaffle_orders"))
    with pytest.raises(UnsupportedCombinationError, match=message + "; use letters, digits and underscores"):
        DagsterOrchestrator().generate(plan, context_of(jaffle_repo))


def test_a_table_named_like_the_output_port_asset_is_refused_instead_of_clashing(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    plan = plan_of(jaffle_repo, "sa_jaffle_orders")
    tables = tuple(replace(t, name="output_ports") if t.name == "orders" else t for t in plan.tables)
    with pytest.raises(UnsupportedCombinationError, match=r"Dagster name 'sa_jaffle_orders__output_ports' .* twice"):
        DagsterOrchestrator().generate(replace(plan, tables=tables), context_of(jaffle_repo))


def test_generate_writes_the_module_next_to_where_airflow_writes_its_dag_file(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    result = generate_repo(jaffle_repo)
    assert result.report.ok, result.report
    module = (jaffle_repo / "generated/sa_jaffle_orders.py").read_text()
    assert module.startswith(
        "# Generated by datapatchbay from dataproducts/sa_jaffle_orders/dataproduct.yaml. "
        "Do not edit: `dpb generate` overwrites this file.\n"
    )
    assert module.endswith("    schedules=[\n        schedule,\n    ],\n)\n")
    assert module == SNAPSHOT.read_text()


def use_container_runtime(root: Path, runtime: str) -> None:
    use_dagster(root)
    (root / "datapatchbay.yaml").write_text(SETTINGS.replace("runtime: worker", f"runtime: {runtime}\nimage: img:1"))


@pytest.mark.parametrize("runtime", ["docker", "kubernetes"])
def test_validate_reports_a_container_runtime_with_dagster_naming_runtime_and_orchestrator(
    jaffle_repo: Path, runtime: str
):
    use_container_runtime(jaffle_repo, runtime)
    messages = [problem.render() for problem in validate_repo(jaffle_repo).problems]
    assert any(
        message.startswith("dataproducts/")
        and f"the {runtime} runtime cannot render tasks for orchestrator 'dagster'" in message
        for message in messages
    ), messages
    result = generate_repo(jaffle_repo)
    assert not result.report.ok
    assert "data product" in result.report.problems[0].message
    assert not (jaffle_repo / "generated").exists()


def test_validate_reports_a_name_that_dagster_does_not_accept(jaffle_repo: Path):
    use_dagster(jaffle_repo)
    (jaffle_repo / "datapatchbay.yaml").write_text(SETTINGS + "connection: my-dwh\n")
    messages = [problem.render() for problem in validate_repo(jaffle_repo).problems]
    assert any("connection 'my-dwh' (resource key) is not a valid Dagster name" in message for message in messages)
    result = generate_repo(jaffle_repo)
    assert not result.report.ok
    assert "data product" in result.report.problems[0].message
    assert not (jaffle_repo / "generated").exists()


def test_the_validate_command_exits_non_zero_for_a_container_runtime_with_dagster(
    jaffle_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    use_container_runtime(jaffle_repo, "docker")
    monkeypatch.chdir(jaffle_repo)
    result = CliRunner().invoke(app, ["validate"])
    assert result.exit_code != 0
    assert "the docker runtime cannot render tasks for orchestrator 'dagster'" in result.output
