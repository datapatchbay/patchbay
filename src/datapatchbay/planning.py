"""Turning the loaded repo into the plans that plugins generate from, with settings resolved over the cascade."""

from pathlib import PurePosixPath

from datapatchbay.cascade import resolve_setting, resolve_settings
from datapatchbay.errors import DatapatchbayError
from datapatchbay.models import DataProductInputPortFile, OutputPortFile, SourceInputPortFile
from datapatchbay.naming import DerivedNames, derive_names
from datapatchbay.plugins import DataProductPlan, SourceSchedule, TablePlan
from datapatchbay.repomodel import DataProduct, Repo
from datapatchbay.settings import EffectiveSettings


def plan_dataproducts(repo: Repo, settings: EffectiveSettings) -> list[DataProductPlan]:
    """Plan every data product of a valid repo, in the order of the repo.

    Args:
        repo: A repo that passed validation.
        settings: The effective settings at the root.

    Returns:
        One plan per data product. Each plan holds the orchestrator, warehouse, executor and runtime names that the
        settings give, whether or not a plugin of that name exists.
    """
    names = {dataproduct.folder: _names_of(dataproduct, settings) for dataproduct in repo.dataproducts}
    roles = {folder: derived.role for folder, derived in names.items()}
    plans = []
    for dataproduct in repo.dataproducts:
        orchestrator = resolve_setting("orchestrator", settings, dataproduct=dataproduct)
        plans.append(_plan(dataproduct, settings, str(orchestrator.value), names[dataproduct.folder], roles))
    return plans


def _names_of(dataproduct: DataProduct, settings: EffectiveSettings) -> DerivedNames:
    model = dataproduct.file.model
    return derive_names(settings.values.conventions, name=model.name, kind_name=model.kind)


def _plan(
    dataproduct: DataProduct, settings: EffectiveSettings, orchestrator: str, names: DerivedNames, roles: dict[str, str]
) -> DataProductPlan:
    tables = []
    for port in dataproduct.ports:
        for table in port.tables:
            resolved = resolve_settings(settings, dataproduct=dataproduct, port=port, table=table)
            build = table.file.model.build
            path, _, function = build.entrypoint.rpartition(":")
            image = resolved["image"].value
            tables.append(
                TablePlan(
                    dataproduct=dataproduct.folder,
                    port=port.name,
                    name=table.name,
                    entrypoint=PurePosixPath(path),
                    function=function,
                    params=build.params,
                    needs=tuple(build.needs),
                    executor=str(resolved["executor"].value),
                    runtime=str(resolved["runtime"].value),
                    image=None if image is None else str(image),
                    severity=resolved["severity"].value,
                    port_source=port,
                    source=table,
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


def _in_build_order(tables: list[TablePlan]) -> tuple[TablePlan, ...]:
    """Order tables so that each one follows the tables it needs; ties keep the order of the files."""
    by_name = {table.name: table for table in tables}
    ordered: list[TablePlan] = []
    done: set[str] = set()

    def visit(table: TablePlan, path: tuple[str, ...]) -> None:
        if table.name in done:
            return
        if table.name in path:  # `dpb validate` rejects cycles, so a plan of a valid repo has none
            raise DatapatchbayError(f"`needs` forms a cycle through table '{table.name}'")
        for need in table.needs:
            if need in by_name:
                visit(by_name[need], (*path, table.name))
        done.add(table.name)
        ordered.append(table)

    for table in tables:
        visit(table, ())
    return tuple(ordered)
