"""Fake plugins and a way to register them in tests, so a test does not depend on what is installed."""

from collections.abc import Callable, Sequence
from pathlib import PurePosixPath
from typing import Any

import pytest

from datapatchbay import registry
from datapatchbay.plugins import DataProductPlan, GeneratedFile, GenerationContext, SqlTask, TablePlan
from datapatchbay.registry import PluginKind


class FakeEntryPoint:
    """Stands in for an `importlib.metadata.EntryPoint`."""

    def __init__(self, name: str, target: Callable[[], object]) -> None:
        self.name = name
        self._target = target

    def load(self) -> Callable[[], object]:
        return self._target


def register(monkeypatch: pytest.MonkeyPatch, kind: PluginKind, name: str, factory: Callable[[], object]) -> None:
    """Add a plugin next to the ones that are installed. Call it again to add more."""
    discover_installed = registry.entry_points

    def discover(*, group: str) -> Sequence[Any]:
        found: list[Any] = list(discover_installed(group=group))
        if group == registry.GROUPS[kind]:
            found.append(FakeEntryPoint(name, factory))
        return found

    monkeypatch.setattr(registry, "entry_points", discover)


class FakeOrchestrator:
    """Write one text file per data product that lists its tables, and remember what it was asked."""

    def __init__(self) -> None:
        self.plans: list[DataProductPlan] = []

    def generate(self, plan: DataProductPlan, context: GenerationContext) -> Sequence[GeneratedFile]:
        self.plans.append(plan)
        tables = ",".join(table.name for table in plan.tables)
        return [GeneratedFile(PurePosixPath(f"{plan.folder}.txt"), f"{plan.folder}: {tables}\n")]


class FakeWarehouse:
    """Contribute one audit task per table and one apply task, as a warehouse with SQL would."""

    def apply_tasks(self, dataproduct: DataProductPlan) -> Sequence[SqlTask]:
        return [SqlTask("apply_grants", f"GRANT USAGE ON SCHEMA {dataproduct.folder} TO reader;")]

    def audit_tasks(self, table: TablePlan) -> Sequence[SqlTask]:
        return [SqlTask(f"audit_{table.name}", f"SELECT 'it''s' FROM {table.name} WHERE false")]
