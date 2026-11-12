"""The dbt sources through which a dbt model reads another data product's output port, generated (ADR-0018).

"Source" here is dbt's word for a declared table, not the glossary's source. For each input port that reads an output
port, one dbt source is written, named after the output port, pointing at its schema and listing the tables of the
producer with their names, descriptions and columns. Quality rules, freshness and access stay on the output port.
Source names are unique in a dbt project and several data products can read one port, so the source of a port is
written once, in `models/_sources.yml` of the first reading data product built by dbt, in name order.
Nothing here imports or runs dbt (ADR-0004).
"""

from collections.abc import Sequence
from typing import Any

from datapatchbay.dbt import DBT_EXECUTOR, MODELS_FOLDER
from datapatchbay.dbt_properties import dump_yaml, generate_dbt_properties, header
from datapatchbay.dbt_tests import generate_dbt_tests
from datapatchbay.plugins import DataProductPlan, GeneratedFile
from datapatchbay.repomodel import Port, Table
from datapatchbay.settings import EffectiveSettings

SOURCES_FILE = "_sources.yml"
"""The file in a data product's `models/` folder that holds the dbt sources it owns."""


def generate_dbt_files(plans: Sequence[DataProductPlan], settings: EffectiveSettings) -> list[GeneratedFile]:
    """Generate every committed dbt file: the properties and singular tests of tables and the sources of input ports.

    Returns:
        The files, with paths relative to the repo root, sorted by path.
    """
    files = [
        *generate_dbt_properties(plans, settings),
        *generate_dbt_sources(plans),
        *generate_dbt_tests(plans, settings),
    ]
    return sorted(files, key=lambda file: file.path)


def generate_dbt_sources(plans: Sequence[DataProductPlan]) -> list[GeneratedFile]:
    """Generate `models/_sources.yml` for the data products that own a dbt source.

    Args:
        plans: The plans of a valid repo.

    Returns:
        The files, sorted by path. Empty when no data product built by dbt reads an output port.
    """
    outputs = {port.name: port for plan in plans for port in plan.source.outputs}
    owners: dict[str, DataProductPlan] = {}  # output port name -> the first reader built by dbt, in name order
    for plan in sorted(plans, key=lambda plan: plan.folder):
        if any(table.executor == DBT_EXECUTOR for table in plan.tables):
            for read in plan.reads:
                owners.setdefault(read, plan)

    files: list[GeneratedFile] = []
    for plan in sorted({owner.folder: owner for owner in owners.values()}.values(), key=lambda plan: plan.folder):
        ports = [outputs[name] for name, owner in sorted(owners.items()) if owner is plan]
        origin = ", ".join(str(table.file.path) for port in ports for table in port.tables)
        content = header(origin) + dump_yaml({"sources": [_source(port) for port in ports]})
        files.append(GeneratedFile(plan.source.file.path.parent / MODELS_FOLDER / SOURCES_FILE, content))
    return sorted(files, key=lambda file: file.path)


def _source(port: Port) -> dict[str, Any]:
    # The schema of an output port is named after it (ADR-0002).
    return {"name": port.name, "schema": port.name, "tables": [_table(table) for table in port.tables]}


def _table(table: Table) -> dict[str, Any]:
    contract = table.file.model
    entry: dict[str, Any] = {"name": table.name}
    if contract.description is not None:
        entry["description"] = contract.description
    columns = []
    for column in contract.columns:
        item: dict[str, Any] = {"name": column.name}
        if column.description is not None:
            item["description"] = column.description
        columns.append(item)
    entry["columns"] = columns
    return entry
