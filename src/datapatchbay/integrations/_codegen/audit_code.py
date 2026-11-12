"""The audit task of the `airflow` orchestrator: the code that runs quality rules, written into the DAG file.

The DAG file may not import datapatchbay (ADR-0001), so the code that runs the checks is a string that the
orchestrator copies into it.
"""

from datapatchbay.integrations._codegen.literals import python_literal
from datapatchbay.plugins import AuditTask, RenderedTask

RUN_AUDIT_HELPER = '''\
def _run_audit(checks, count_violations):
    """Run every check. Log a broken `warning` rule; fail after all checks if an `error` rule is broken."""
    errors = []
    for check in checks:
        violations = count_violations(check["sql"])
        if not violations:
            continue
        where = f"table '{check['table']}'" + (f", column '{check['column']}'" if check["column"] else "")
        message = f"quality rule '{check['rule']}' is broken on {where}: {violations} violation(s)"
        if check["severity"] == "error":
            errors.append(message)
        else:
            logging.getLogger(__name__).warning(message)
    if errors:
        raise RuntimeError("; ".join(errors))'''
"""The part of the audit code that does not depend on the orchestrator; the `local` orchestrator reuses it."""

_AIRFLOW_AUDIT_TASK = '''\
def _audit_task(task_id, conn_id, checks):
    """Create a task that runs the checks of a table through the orchestrator's connection to the warehouse."""

    @task(task_id=task_id)
    def audit():
        hook = BaseHook.get_connection(conn_id).get_hook()
        _run_audit(checks, lambda sql: hook.get_first(sql)[0])

    return audit()'''

AUDIT_HELPER = RUN_AUDIT_HELPER + "\n\n\n" + _AIRFLOW_AUDIT_TASK


def check_rows(audit: AuditTask) -> list[dict[str, str | None]]:
    """Return the checks of an audit as the plain dicts that the generated `_run_audit` reads."""
    return [
        {"rule": c.rule, "table": c.table, "column": c.column, "severity": c.severity, "sql": c.sql}
        for c in audit.checks
    ]


def render_audit_task(audit: AuditTask, *, connection: str, variable: str) -> RenderedTask:
    """Render an audit task for an Airflow DAG file.

    Args:
        audit: The audit of one table.

    Keyword Args:
        connection: Name of the Airflow connection to the warehouse.
        variable: The name that the task is assigned to.

    Raises:
        ValueError: If a value cannot be written as a Python literal.
    """
    arguments = ", ".join(
        [python_literal(audit.task_id), python_literal(connection), python_literal(check_rows(audit))]
    )
    return RenderedTask(
        imports=("import logging", "from airflow.sdk import BaseHook", "from airflow.sdk import task"),
        helpers=(AUDIT_HELPER,),
        lines=(f"{variable} = _audit_task({arguments})",),
    )
