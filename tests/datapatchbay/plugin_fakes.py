"""Fake plugins and a way to register them in tests, so a test does not depend on what is installed."""

from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath
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


def install_distribution(monkeypatch: pytest.MonkeyPatch, site: Path, kind: PluginKind, name: str, target: str) -> None:
    """Install a distribution whose metadata registers a plugin, so it is found as a real third-party plugin.

    Writes `entry_points.txt` into a `*.dist-info` folder under `site` and puts `site` on `sys.path`, which is what
    `pip install` does for a package. Nothing in `datapatchbay.registry` is replaced.

    Args:
        monkeypatch: Restores `sys.path` after the test.
        site: An empty folder to act as site-packages.
        kind: The extension point.
        name: The plugin's name, as written in the settings.
        target: The `module:attribute` of the plugin class, which must be importable.
    """
    info = site / "fake_plugin-1.0.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: fake-plugin\nVersion: 1.0\n")
    (info / "entry_points.txt").write_text(f"[{registry.GROUPS[kind]}]\n{name} = {target}\n")
    monkeypatch.syspath_prepend(str(site))


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
