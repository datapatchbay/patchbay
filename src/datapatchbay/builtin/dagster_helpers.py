"""The helper code of the `dagster` orchestrator, which it copies into every generated module.

A generated module may not import datapatchbay (ADR-0001), so the code that runs SQL and builds checks and sensors is
text. The warehouse resource of the module is anything with `get_connection()`, a context manager that yields a
DB-API connection which commits by itself (ADR-0023).
"""

EXECUTE_HELPER = '''\
def _execute(connection, sql):
    """Run SQL, which may hold several statements."""
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
    finally:
        cursor.close()'''

COUNT_HELPER = '''\
def _count_violations(connection, sql):
    """Run a query that returns the number of rows that break a quality rule."""
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
        return cursor.fetchone()[0]
    finally:
        cursor.close()'''

AUDIT_CHECK_HELPER = '''\
def _audit_check(name, key, resource, checks):
    """Create the asset check of a table: one result per quality rule, so each rule shows on its own.

    A broken `error` rule is a blocking check, so the assets downstream of the table do not materialize in the run.
    A broken `warning` rule is reported and the run goes on.
    """
    specs = [dg.AssetCheckSpec(check["name"], asset=key, blocking=check["severity"] == "error") for check in checks]

    @dg.multi_asset_check(name=name, specs=specs, required_resource_keys={resource})
    def audit(context):
        with getattr(context.resources, resource).get_connection() as connection:
            counts = [_count_violations(connection, check["sql"]) for check in checks]
        for check, violations in zip(checks, counts, strict=True):
            where = f"table '{check['table']}'" + (f", column '{check['column']}'" if check["column"] else "")
            broken = f"quality rule '{check['rule']}' is broken on {where}: {violations} violation(s)"
            yield dg.AssetCheckResult(
                check_name=check["name"],
                asset_key=key,
                passed=violations == 0,
                severity=dg.AssetCheckSeverity.ERROR if check["severity"] == "error" else dg.AssetCheckSeverity.WARN,
                metadata={"violations": violations},
                description=broken if violations else None,
            )

    return audit'''

SQL_CHECK_HELPER = '''\
def _sql_check(name, check_name, key, resource, sql):
    """Create a blocking asset check that passes when the SQL runs without raising an error."""

    @dg.multi_asset_check(
        name=name,
        specs=[dg.AssetCheckSpec(check_name, asset=key, blocking=True)],
        required_resource_keys={resource},
    )
    def audit(context):
        with getattr(context.resources, resource).get_connection() as connection:
            _execute(connection, sql)
        yield dg.AssetCheckResult(check_name=check_name, asset_key=key, passed=True)

    return audit'''

READ_SENSOR_HELPER = '''\
def _read_sensor(name, port, job):
    """Create a sensor that runs the job when an output port that the data product reads is materialized.

    The run key is the run that materialized the port, so one upstream run never starts the job twice.
    """

    @dg.asset_sensor(
        asset_key=dg.AssetKey([port]), job=job, name=name, default_status=dg.DefaultSensorStatus.RUNNING
    )
    def sensor(context, asset_event):
        yield dg.RunRequest(run_key=asset_event.run_id)

    return sensor'''
