"""The dbt properties of the tables that dbt builds, generated from the table files (ADR-0013).

For each such table this writes the properties file of its model, next to the model, and for each data product with
such a table one file with its dbt group. The files are committed, so the output must be the same for the same input:
keys come in a fixed order and lists keep the order of the table file. Nothing here imports or runs dbt (ADR-0004).

Table rules (`primary_key`, `row_count`, `sql`) are generated as singular tests by `dbt_tests` (ADR-0019).
"""

from collections.abc import Sequence
from io import StringIO
from typing import Any

from ruamel.yaml import YAML

from datapatchbay.dbt import DBT_EXECUTOR, MODELS_FOLDER, model_name
from datapatchbay.genheader import generated_header
from datapatchbay.models.table import AcceptedValuesRule, Column, NotNullRule, UniqueRule
from datapatchbay.plugins import DataProductPlan, GeneratedFile, TablePlan
from datapatchbay.settings import EffectiveSettings
from datapatchbay.sqlquote import standard_literal

GROUP_FILE = "_group.yml"
"""The file in a data product's `models/` folder that holds its dbt group."""

SEVERITY = {"error": "error", "warning": "warn"}
"""Severity of a rule as dbt spells it. `dbt_import` reads it the other way round."""


def generate_dbt_properties(plans: Sequence[DataProductPlan], settings: EffectiveSettings) -> list[GeneratedFile]:
    """Generate the dbt properties files of every table built by dbt.

    Args:
        plans: The plans of a valid repo.
        settings: The effective settings, which hold the `dbt_model` naming template.

    Returns:
        The files, with paths relative to the repo root, sorted by path. Empty when dbt builds no table.
    """
    files: list[GeneratedFile] = []
    for plan in plans:
        tables = [table for table in plan.tables if table.executor == DBT_EXECUTOR]
        if not tables:
            continue
        models = plan.source.file.path.parent / MODELS_FOLDER
        files.append(
            GeneratedFile(models / GROUP_FILE, generated_header(plan.source.file.path) + dump_yaml(_group(plan)))
        )
        for table in tables:
            name = model_name(settings, plan.source, table.source)
            assert name is not None, "dpb validate guarantees a model name for a table built by dbt"
            content = generated_header(table.source.file.path) + dump_yaml({"models": [_model(plan, table, name)]})
            files.append(GeneratedFile(models / f"{name}.yml", content))
    return sorted(files, key=lambda file: file.path)


def _group(plan: DataProductPlan) -> dict[str, Any]:
    return {"groups": [{"name": plan.folder, "owner": {"name": plan.owner}}]}


def _model(plan: DataProductPlan, table: TablePlan, name: str) -> dict[str, Any]:
    contract = table.source.file.model
    model: dict[str, Any] = {"name": name}
    if contract.description is not None:
        model["description"] = contract.description
    model["config"] = {
        "contract": {"enforced": True},
        "alias": table.name,
        "schema": plan.names.private_port,
        "group": plan.folder,
    }
    model["columns"] = [_column(column, table) for column in contract.columns]
    return model


def _column(column: Column, table: TablePlan) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": column.name, "data_type": column.type}
    if column.description is not None:
        entry["description"] = column.description
    if column.pii:
        entry["config"] = {"meta": {"pii": True}}
    tests = []
    for rule in column.rules:
        severity = table.severity_of(rule.severity)
        if severity != "none":
            tests.append(_data_test(rule, SEVERITY[severity]))
    if tests:
        entry["data_tests"] = tests
    return entry


def _data_test(rule: NotNullRule | UniqueRule | AcceptedValuesRule, severity: str) -> dict[str, Any]:
    config = {"config": {"severity": severity}}
    if not isinstance(rule, AcceptedValuesRule):
        return {rule.rule: config}
    if all(isinstance(value, str) for value in rule.values):
        return {rule.rule: {"arguments": {"values": list(rule.values)}, **config}}
    # dbt quotes every value by default. Numbers and booleans must stay bare, so strings become SQL literals.
    values = [standard_literal(value) if isinstance(value, str) else value for value in rule.values]
    return {rule.rule: {"arguments": {"values": values, "quote": False}, **config}}


def dump_yaml(document: dict[str, Any]) -> str:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.width = 10_000
    yaml.indent(mapping=2, sequence=4, offset=2)
    buffer = StringIO()
    yaml.dump(document, buffer)
    return buffer.getvalue()
