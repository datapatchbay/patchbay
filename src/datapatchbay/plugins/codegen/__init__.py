"""Code-generation toolkit for orchestrator and runtime plugins: build order, audit code and Python literals.

This module is public, not yet stable in milestone 1: names may change before the plugin interface is declared
stable (ADR-0009). Generated files never import datapatchbay (ADR-0001), so what this toolkit returns is source text.
"""

from datapatchbay.plugins.codegen.audit_code import AUDIT_HELPER, RUN_AUDIT_HELPER, check_rows, render_audit_task
from datapatchbay.plugins.codegen.literals import python_literal
from datapatchbay.plugins.codegen.table_builds import TableBuilds, plan_builds, render_build

__all__ = [
    "AUDIT_HELPER",
    "RUN_AUDIT_HELPER",
    "TableBuilds",
    "check_rows",
    "plan_builds",
    "python_literal",
    "render_audit_task",
    "render_build",
]
