"""The plugin package keeps one import path for plugin authors and gives each module one job."""

import importlib

import pytest

import datapatchbay.plugins as plugins

MODULE_OF = {
    "interfaces": [
        "BatchesBuilds",
        "ChecksDataProducts",
        "ChecksPlans",
        "ChecksTables",
        "CommittedOutput",
        "DeclaredSettings",
        "DeclaresSettings",
        "Executor",
        "GenerationContext",
        "NamingTemplate",
        "Orchestrator",
        "OwnsQualityRules",
        "RenderKind",
        "Runtime",
        "ScaffoldsTables",
        "UnsupportedCombinationError",
        "Warehouse",
        "WritesCommittedFiles",
    ],
    "plan": [
        "DataProductPlan",
        "NewTable",
        "PlannedRepo",
        "SourceSchedule",
        "TablePlan",
    ],
    "tasks": [
        "AuditCheck",
        "AuditTask",
        "BuildCall",
        "BuildTask",
        "CommandCall",
        "GeneratedFile",
        "PythonCall",
        "RenderedTask",
        "ScaffoldedTable",
        "SqlTask",
    ],
}


@pytest.mark.parametrize(("module", "name"), [(m, n) for m, names in MODULE_OF.items() for n in names])
def test_a_name_is_reexported_from_its_module(module: str, name: str) -> None:
    defined = importlib.import_module(f"datapatchbay.plugins.{module}")
    assert getattr(plugins, name) is getattr(defined, name)
    assert name in plugins.__all__


def test_the_package_exports_nothing_else() -> None:
    assert sorted(plugins.__all__) == sorted(n for names in MODULE_OF.values() for n in names)


def test_plan_data_names_no_plugin_interface() -> None:
    plan = importlib.import_module("datapatchbay.plugins.plan")
    assert not {"Executor", "Runtime", "Warehouse", "Orchestrator", "BuildTask"} & set(vars(plan))
