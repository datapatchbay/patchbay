"""The plugin interface (ADR-0009), re-exported so a plugin imports it from one place.

- `interfaces`: the four extension points, as `Protocol` classes, with `GenerationContext` and the error
  a plugin raises.
- `plan`: the plan data that `dpb generate` hands to plugins.
- `tasks`: the tasks, calls and files that plugins hand back.
- `registry`: finding plugins through entry points. Not re-exported: it loads plugins and is not part of
  their interface.
"""

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
