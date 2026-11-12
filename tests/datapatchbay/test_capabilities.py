"""The core asks executors for optional capabilities and never names one (ADR-0024)."""

from collections.abc import Sequence
from pathlib import Path, PurePosixPath

import pytest
from plugin_fakes import register

from datapatchbay.capabilities import ExecutorPlugins
from datapatchbay.generate import generate_repo
from datapatchbay.integrations.dbt.executor import DbtExecutor
from datapatchbay.integrations.docker.runtime import DockerRuntime
from datapatchbay.integrations.python.executor import PythonExecutor
from datapatchbay.integrations.worker.runtime import WorkerRuntime
from datapatchbay.plugins import (
    BatchesBuilds,
    ChecksDataProducts,
    ChecksPlans,
    ChecksTables,
    CommandCall,
    OwnsQualityRules,
    PlannedRepo,
    PythonCall,
    ScaffoldsTables,
    WritesCommittedFiles,
)
from datapatchbay.problems import Problem
from datapatchbay.repomodel import DataProduct, Repo, Table
from datapatchbay.scaffold import NewDataProduct, ScaffoldError, render_files
from datapatchbay.settings import EffectiveSettings, load_settings
from datapatchbay.validation import validate_repo

COMMITTED = PurePosixPath("spark-notes.txt")


class FakeOutput:
    """The committed output of a fake executor: one note file that has to exist and match."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self.orphans: tuple[PurePosixPath, ...] = ()
        self.error: str | None = None

    def problems(self) -> list[Problem]:
        if (self._root / COMMITTED).is_file():
            return []
        return [Problem(COMMITTED, None, "note is missing; run `dpb generate` to refresh it")]

    def write(self) -> tuple[PurePosixPath, ...]:
        (self._root / COMMITTED).write_text("note\n")
        return (COMMITTED,)


class Spark(PythonExecutor):
    """A third-party executor that builds like python and adds a capability of each kind it can."""

    def committed_output(self, planned: PlannedRepo) -> FakeOutput:
        return FakeOutput(planned.repo.root)

    def check_dataproduct(self, repo: Repo, dataproduct: DataProduct) -> Sequence[Problem]:
        return []

    def check_plans(self, planned: PlannedRepo) -> Sequence[Problem]:
        return [Problem(PurePosixPath("plans"), None, f"{len(planned.plans)} plan(s) seen by spark")]

    def check_table(self, settings: EffectiveSettings, dataproduct: DataProduct, table: Table) -> Sequence[Problem]:
        return []


@pytest.fixture
def spark_repo(jaffle_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    register(monkeypatch, "executor", "spark", Spark)
    return jaffle_repo


def test_the_built_in_executors_have_the_capabilities_they_need():
    for capability in (
        WritesCommittedFiles,
        ChecksDataProducts,
        ChecksTables,
        ChecksPlans,
        BatchesBuilds,
        OwnsQualityRules,
        ScaffoldsTables,
    ):
        assert isinstance(DbtExecutor(), capability)
    assert isinstance(PythonExecutor(), ChecksTables)
    assert isinstance(PythonExecutor(), ScaffoldsTables)
    for capability in (WritesCommittedFiles, ChecksDataProducts, ChecksPlans, BatchesBuilds, OwnsQualityRules):
        assert not isinstance(PythonExecutor(), capability)


def test_a_runtime_lists_the_types_of_call_it_can_run():
    assert WorkerRuntime.call_types == (PythonCall, CommandCall)
    assert DockerRuntime.call_types == (PythonCall,)
    assert DbtExecutor.call_type is CommandCall


def test_the_installed_executors_with_a_capability_come_in_the_order_of_their_names(spark_repo: Path):
    found = ExecutorPlugins().with_capability(ChecksPlans)
    assert [type(executor) for executor in found] == [DbtExecutor, Spark]


def test_an_executor_that_is_not_installed_has_no_plugin(spark_repo: Path):
    assert ExecutorPlugins().get("flink") is None
    assert isinstance(ExecutorPlugins().get("spark"), Spark)


def test_validate_asks_a_third_party_executor_for_its_checks_and_committed_files(spark_repo: Path):
    messages = [problem.render() for problem in validate_repo(spark_repo).problems]
    assert "spark-notes.txt: note is missing; run `dpb generate` to refresh it" in messages
    assert any(m.startswith("plans: ") and m.endswith("plan(s) seen by spark") for m in messages)


def test_a_stage_1_problem_of_an_executor_stops_validate_before_stage_2(
    spark_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    def check(self: Spark, repo: Repo, dataproduct: DataProduct) -> Sequence[Problem]:
        return [Problem(PurePosixPath(dataproduct.folder), None, "checked by spark")]

    monkeypatch.setattr(Spark, "check_dataproduct", check)
    messages = [problem.render() for problem in validate_repo(spark_repo).problems]
    assert messages
    assert all(message.endswith(": checked by spark") for message in messages)


def test_generate_writes_the_committed_files_of_a_third_party_executor(spark_repo: Path):
    result = generate_repo(spark_repo)
    assert result.report.ok
    assert COMMITTED in result.committed
    assert (spark_repo / COMMITTED).read_text() == "note\n"
    assert [p.render() for p in validate_repo(spark_repo).problems if p.file == COMMITTED] == []


def test_an_output_that_cannot_be_written_stops_generate_before_anything_is_written(
    spark_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    def broken(self: Spark, planned: PlannedRepo) -> FakeOutput:
        output = FakeOutput(planned.repo.root)
        output.error = "spark has nowhere to write"
        return output

    monkeypatch.setattr(Spark, "committed_output", broken)
    with pytest.raises(Exception, match="spark has nowhere to write"):
        generate_repo(spark_repo)
    assert not (spark_repo / COMMITTED).exists()


def test_the_checks_of_a_python_table_report_a_missing_entrypoint_by_the_executor(jaffle_repo: Path):
    path = jaffle_repo / "dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/orders.yaml"
    path.write_text(path.read_text().replace("entrypoint:", "image: x\n  #"))
    assert any(
        "needs a `build.entrypoint`, because its executor is 'python'" in p.message
        for p in validate_repo(jaffle_repo).problems
    )


def new(executor: str) -> NewDataProduct:
    return NewDataProduct(name="foo", kind="source-aligned", owner="me", executor=executor)


def test_dpb_new_asks_the_executor_for_the_stub_of_each_table(jaffle_repo: Path):
    conventions = load_settings(jaffle_repo).values.conventions
    files = render_files(conventions, new("python"))
    assert "dataproducts/sa_foo/src/example.py" in files
    assert "entrypoint: src/example.py:build" in files["dataproducts/sa_foo/outputs/sa_foo/example.yaml"]
    files = render_files(conventions, new("dbt"))
    assert "dataproducts/sa_foo/models/sa_foo__example.sql" in files
    assert "build" not in files["dataproducts/sa_foo/outputs/sa_foo/example.yaml"]


def test_dpb_new_refuses_an_executor_that_cannot_scaffold_tables(jaffle_repo: Path, monkeypatch: pytest.MonkeyPatch):
    class Bare:
        def call(self, table: object) -> None: ...

    register(monkeypatch, "executor", "bare", Bare)
    with pytest.raises(ScaffoldError, match="executor 'bare' cannot scaffold tables"):
        render_files(load_settings(jaffle_repo).values.conventions, new("bare"))
