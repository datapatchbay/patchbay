"""The plan data: what `dpb generate` works out for a data product and hands to the plugins (ADR-0009).

Plain frozen values with the settings resolved over the cascade. They name no plugin interface and no task; the
tasks the plugins hand back are in `tasks`, the interfaces in `interfaces`.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from datapatchbay.files.repomodel import DataProduct, Port, Repo, Table
from datapatchbay.models.base import Severity
from datapatchbay.problems import Report

if TYPE_CHECKING:
    from datapatchbay.settings.effective import EffectiveSettings, ResolvedConventions
    from datapatchbay.settings.naming import DerivedNames

__all__ = ["DataProductPlan", "NewTable", "PlannedRepo", "SourceSchedule", "TablePlan"]


@dataclass(frozen=True, slots=True)
class TablePlan:
    """One table to build, with its settings resolved over the cascade.

    Attributes:
        dataproduct: Folder name of the data product the table belongs to.
        port: Name of the port the table is in.
        name: Name of the table.
        schema: Schema in the warehouse that holds the built table: the private port of the data product, named by
            its naming template. Output ports only hold views over it.
        entrypoint: The file of the build function, relative to the data product folder; `None` for a table whose
            executor needs no build function.
        function: Name of the build function; `None` when there is no entrypoint.
        params: Parameters passed to the function.
        needs: Names of the tables of the same data product that are built first.
        executor: Name of the executor plugin.
        runtime: Name of the runtime plugin.
        image: Container image for container runtimes, or `None`.
        container: Free-form settings for the container task, as written in the files; dpb does not read them.
        severity: Default severity of the table's quality rules.
        port_source: The loaded port, for plugins that need its contract or access policy.
        source: The loaded table, for plugins that need its columns and quality rules.
        directory: Absolute path of the data product folder the table belongs to.
        root: Absolute path of the repo root.
        plugin_settings: The resolved settings section of each plugin that declares one, by plugin name (ADR-0025).
    """

    dataproduct: str
    port: str
    name: str
    schema: str
    entrypoint: PurePosixPath | None
    function: str | None
    params: Mapping[str, Any]
    needs: tuple[str, ...]
    executor: str
    runtime: str
    image: str | None
    severity: Severity
    port_source: Port
    source: Table
    container: Mapping[str, Any] = field(default_factory=dict)
    directory: Path = Path()
    root: Path = Path()
    plugin_settings: Mapping[str, BaseModel] = field(default_factory=dict)

    def severity_of(self, rule_severity: Severity | None) -> Severity:
        """Return the severity of a rule: its own, or the table's default when the rule sets none."""
        return rule_severity or self.severity


@dataclass(frozen=True, slots=True)
class SourceSchedule:
    """A source input port and the cron expression at which its source delivers data."""

    port: str
    cron: str


@dataclass(frozen=True, slots=True)
class DataProductPlan:
    """Everything an orchestrator needs to generate one data product's DAG.

    Attributes:
        folder: Folder name of the data product, which is also its DAG id.
        name: Name of the data product.
        owner: The owner, free text.
        directory: Absolute path of the data product folder.
        orchestrator: Name of the orchestrator plugin.
        warehouse: Name of the warehouse plugin.
        connection: Name of the orchestrator's connection to the warehouse.
        tables: Every table, ordered so that a table comes after the tables in its `needs`.
        source_schedules: The input ports fed by a source, sorted by port name.
        reads: Names of the output ports of other data products that this data product reads, sorted.
        outputs: Names of the output ports, sorted.
        source: The loaded data product, for plugins that need its files.
        names: The names the naming templates produce for this data product, such as its private port and role.
        roles: The role of every data product in the repo, by folder name, for `product:` readers.
        plugin_settings: The resolved settings section of each plugin that declares one, by plugin name (ADR-0025).
    """

    folder: str
    name: str
    owner: str
    directory: Path
    orchestrator: str
    warehouse: str
    connection: str
    tables: tuple[TablePlan, ...]
    source_schedules: tuple[SourceSchedule, ...]
    reads: tuple[str, ...]
    outputs: tuple[str, ...]
    source: DataProduct
    names: "DerivedNames"
    roles: Mapping[str, str]
    plugin_settings: Mapping[str, BaseModel] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlannedRepo:
    """A repo that passed stage 1, with its data products planned exactly once.

    Every check and renderer after the gate takes this and never plans again. Plugins named in the settings are known
    to exist.

    Attributes:
        repo: What loaded.
        settings: The effective settings, built once from the root file.
        plans: One plan per data product, in the order of the repo.
    """

    repo: Repo
    settings: "EffectiveSettings"
    plans: list[DataProductPlan]

    @property
    def report(self) -> Report:
        """The report of a repo with no problems."""
        return Report(dataproducts_checked=self.repo.dataproduct_dirs, problems=[])


@dataclass(frozen=True, slots=True)
class NewTable:
    """A table that `dpb new` is about to write, for the executor that builds it.

    Attributes:
        name: Name of the table.
        needs: Names of the tables of the same data product that are built first.
        dataproduct: Folder name of the new data product.
        dataproduct_name: The bare name given to `dpb new`.
        kind: Kind of the data product.
        conventions: The conventions in the effective settings, which hold the naming templates.
    """

    name: str
    needs: tuple[str, ...]
    dataproduct: str
    dataproduct_name: str
    kind: str
    conventions: "ResolvedConventions"
