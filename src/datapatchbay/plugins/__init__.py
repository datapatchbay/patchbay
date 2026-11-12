"""The plugin interface (ADR-0009), re-exported so a plugin imports it from one place."""

from datapatchbay.plugins.interfaces import (
    Executor,
    GenerationContext,
    Orchestrator,
    Runtime,
    UnsupportedCombinationError,
    Warehouse,
)
from datapatchbay.plugins.plan import DataProductPlan, DbtLocation, PlannedRepo, SourceSchedule, TablePlan
from datapatchbay.plugins.tasks import (
    AuditCheck,
    AuditTask,
    BuildTask,
    DbtCall,
    GeneratedFile,
    PythonCall,
    RenderedTask,
    SqlTask,
)

__all__ = [
    "AuditCheck",
    "AuditTask",
    "BuildTask",
    "DataProductPlan",
    "DbtCall",
    "DbtLocation",
    "Executor",
    "GeneratedFile",
    "GenerationContext",
    "Orchestrator",
    "PlannedRepo",
    "PythonCall",
    "RenderedTask",
    "Runtime",
    "SourceSchedule",
    "SqlTask",
    "TablePlan",
    "UnsupportedCombinationError",
    "Warehouse",
]
