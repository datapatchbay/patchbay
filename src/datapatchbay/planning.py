"""Turning the loaded repo into the plans that plugins generate from, with settings resolved over the cascade."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from datapatchbay.cascade import ResolvedCascade
from datapatchbay.dbt import MODELS_FOLDER
from datapatchbay.models import DataProductInputPortFile, OutputPortFile, SourceInputPortFile
from datapatchbay.naming import DerivedNames, derive_names
from datapatchbay.plugins import DataProductPlan, DbtLocation, SourceSchedule, TablePlan
from datapatchbay.problems import Report
from datapatchbay.repomodel import DataProduct, Repo
from datapatchbay.settings import EffectiveSettings


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
    settings: EffectiveSettings
    plans: list[DataProductPlan]

    @property
    def report(self) -> Report:
        """The report of a repo with no problems."""
        return Report(dataproducts_checked=self.repo.dataproduct_dirs, problems=[])


def plan_dataproducts(repo: Repo, settings: EffectiveSettings, cascade: ResolvedCascade) -> list[DataProductPlan]:
    """Plan every data product of a valid repo, in the order of the repo.

    Args:
        repo: A repo that passed validation.
        settings: The effective settings at the root.
        cascade: The resolved settings of every data product and table.

    Returns:
        One plan per data product. Each plan holds the orchestrator, warehouse, executor and runtime names that the
        settings give, whether or not a plugin of that name exists.
    """
    names = {dataproduct.folder: _names_of(dataproduct, settings) for dataproduct in repo.dataproducts}
    roles = {folder: derived.role for folder, derived in names.items()}
    plans = []
    for dataproduct in repo.dataproducts:
        orchestrator = cascade.for_dataproduct(dataproduct)["orchestrator"]
        plans.append(
            _plan(dataproduct, settings, cascade, str(orchestrator.value), names[dataproduct.folder], roles, repo.root)
        )
    return plans


def _names_of(dataproduct: DataProduct, settings: EffectiveSettings) -> DerivedNames:
    model = dataproduct.file.model
    return derive_names(settings.values.conventions, name=model.name, kind_name=model.kind)


def _plan(
    dataproduct: DataProduct,
    settings: EffectiveSettings,
    cascade: ResolvedCascade,
    orchestrator: str,
    names: DerivedNames,
    roles: Mapping[str, str],
    root: Path,
) -> DataProductPlan:
    dbt = _dbt_location(dataproduct, settings, root)
    tables = []
    for port in dataproduct.ports:
        for table in port.tables:
            resolved = cascade.for_table(table)
            image = resolved["image"].value
            container = resolved["container"].value
            tables.append(
                TablePlan(
                    dataproduct=dataproduct.folder,
                    port=port.name,
                    name=table.name,
                    schema=names.private_port,
                    entrypoint=PurePosixPath(table.entrypoint_path) if table.entrypoint_path else None,
                    function=table.function or None,
                    params=table.params,
                    needs=tuple(table.needs),
                    executor=str(resolved["executor"].value),
                    runtime=str(resolved["runtime"].value),
                    image=None if image is None else str(image),
                    severity=resolved["severity"].value,
                    port_source=port,
                    source=table,
                    container={} if container is None else container,
                    dbt=dbt,
                )
            )

    schedules = []
    reads = []
    for port in dataproduct.inputs:
        model = port.file.model
        if isinstance(model, SourceInputPortFile):
            schedules.append(SourceSchedule(port.name, model.schedule))
        elif isinstance(model, DataProductInputPortFile):
            reads.append(model.from_)
    outputs = [port.name for port in dataproduct.outputs if isinstance(port.file.model, OutputPortFile)]

    return DataProductPlan(
        folder=dataproduct.folder,
        name=dataproduct.file.model.name,
        owner=dataproduct.file.model.owner,
        directory=dataproduct.directory,
        orchestrator=orchestrator,
        warehouse=settings.values.warehouse,
        connection=settings.values.connection,
        tables=_in_build_order(tables),
        source_schedules=tuple(sorted(schedules, key=lambda schedule: schedule.port)),
        reads=tuple(sorted(set(reads))),
        outputs=tuple(sorted(outputs)),
        source=dataproduct,
        names=names,
        roles=roles,
    )


def _dbt_location(dataproduct: DataProduct, settings: EffectiveSettings, root: Path) -> DbtLocation:
    """Place the models of a data product in the dbt project, which the `dbt.project_dir` setting locates."""
    dbt = settings.values.dbt
    models = dataproduct.directory / MODELS_FOLDER
    if PurePosixPath(dbt.project_dir).is_absolute():
        # The project is a copy of the repo's layout somewhere else on the worker: select by the path in the repo.
        project_dir = dbt.project_dir
        select = os.path.relpath(models, root)
    else:
        project = Path(os.path.normpath(root / dbt.project_dir))
        project_dir = Path(os.path.relpath(project, dataproduct.directory)).as_posix()
        select = os.path.relpath(models, project)
    return DbtLocation(
        models=PurePosixPath(Path(select).as_posix()), project_dir=project_dir, profiles_dir=dbt.profiles_dir
    )


def _in_build_order(tables: list[TablePlan]) -> tuple[TablePlan, ...]:
    """Order tables so that each one follows the tables it needs; ties keep the order of the files."""
    by_name = {table.name: table for table in tables}
    ordered: list[TablePlan] = []
    done: set[str] = set()

    def visit(table: TablePlan, path: tuple[str, ...]) -> None:
        if table.name in done:
            return
        if table.name in path:  # `dpb validate` rejects cycles, so a plan of a valid repo has none
            raise RuntimeError(f"`needs` forms a cycle through table '{table.name}'")
        for need in table.needs:
            if need in by_name:
                visit(by_name[need], (*path, table.name))
        done.add(table.name)
        ordered.append(table)

    for table in tables:
        visit(table, ())
    return tuple(ordered)
