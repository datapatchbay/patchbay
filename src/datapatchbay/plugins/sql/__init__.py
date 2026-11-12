"""SQL toolkit for warehouse plugins: audit SQL, port views and quoting.

This module is public, not yet stable in milestone 1: names may change before the plugin interface is declared
stable (ADR-0009). A warehouse plugin imports from here instead of writing its own quality-rule queries and views.
"""

from datapatchbay.plugins.sql.audit_sql import Dialect, audit_checks, audit_tasks
from datapatchbay.plugins.sql.port_views import output_ports, view_sql
from datapatchbay.plugins.sql.sqlquote import standard_identifier, standard_literal

__all__ = [
    "Dialect",
    "audit_checks",
    "audit_tasks",
    "output_ports",
    "standard_identifier",
    "standard_literal",
    "view_sql",
]
