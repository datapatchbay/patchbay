"""Views, masking and grants for the output ports of a data product in Postgres (ADR-0002, ADR-0007, ADR-0017).

The whole apply is one string that the orchestrator runs in one go, so Postgres runs it as one transaction: it
either takes effect completely or not at all. Warehouse roles are expected to exist (ADR-0017); a grant to a role
that does not exist fails the apply.

How one output port is applied:

1. The port's schema is created when missing, and every privilege on the schema is revoked, from `PUBLIC` and from
   every role that was granted any. That is what removes a reader that left `port.yaml`.
2. Each table gets its view dropped and created again. A view cannot lose a column with `CREATE OR REPLACE`, and
   dropping a view also drops every privilege on it, so a reader that was removed has none left. A PII column is
   `CASE WHEN <member of a PII reader role> THEN column ELSE NULL END`.
3. The schema and the views are granted to the readers and the PII readers. Nobody is granted anything on the
   private schema: the views read it with their owner's privileges.
"""

from collections.abc import Iterable, Sequence

from datapatchbay.builtin.audit_sql import Dialect, standard_identifier, standard_literal
from datapatchbay.builtin.port_views import output_ports, view_sql
from datapatchbay.errors import DatapatchbayError
from datapatchbay.models import OutputPortFile, ProductReader
from datapatchbay.plugins import DataProductPlan, TablePlan
from datapatchbay.repomodel import Port

__all__ = ["access_sql"]

_REVOKE_SCHEMA_GRANTS = """\
DO {tag}
DECLARE granted record;
BEGIN
    FOR granted IN
        SELECT acl.grantee FROM pg_namespace AS namespace, aclexplode(namespace.nspacl) AS acl
        WHERE namespace.nspname = {schema_literal} AND acl.grantee <> namespace.nspowner
    LOOP
        EXECUTE 'REVOKE ALL ON SCHEMA ' || quote_ident({schema_literal}) || ' FROM '
            || CASE WHEN granted.grantee = 0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(granted.grantee)) END;
    END LOOP;
END
{tag};"""


_DIALECT = Dialect(identifier=standard_identifier, literal=standard_literal)


def _dollar_tag(text: str) -> str:
    """Return a dollar-quote tag that does not occur in `text`, so that text cannot end the quoted body."""
    tag = "$body$"
    while tag in text:
        tag = f"${tag[1:-1]}x$"
    return tag


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def access_sql(plan: DataProductPlan) -> str:
    """Return the statements that apply the views and grants of every output port, or `""` when there are none."""
    return "\n\n".join(_port_sql(plan, port, tables) for port, tables in output_ports(plan))


def _port_sql(plan: DataProductPlan, port: Port, tables: Sequence[TablePlan]) -> str:
    model = port.file.model
    assert isinstance(model, OutputPortFile)
    readers = {_role_of(plan, reader) for reader in model.access.readers}
    pii_readers = sorted(set(model.access.pii_readers))
    everyone = sorted(readers | set(pii_readers))
    schema = _DIALECT.identifier(port.name)
    statements = [
        f"-- Output port {' '.join(port.name.split())}",
        f"CREATE SCHEMA IF NOT EXISTS {schema};",
        _REVOKE_SCHEMA_GRANTS.format(schema_literal=_literal(port.name), tag=_dollar_tag(port.name)),
    ]
    for table in tables:
        statements += [
            f"DROP VIEW IF EXISTS {schema}.{_DIALECT.identifier(table.name)};",
            _view_sql(table, pii_readers),
        ]
    if everyone:
        roles = ", ".join(_DIALECT.identifier(role) for role in everyone)
        statements.append(f"GRANT USAGE ON SCHEMA {schema} TO {roles};")
        statements += [f"GRANT SELECT ON {schema}.{_DIALECT.identifier(table.name)} TO {roles};" for table in tables]
    return "\n".join(statements)


def _role_of(plan: DataProductPlan, reader: str | ProductReader) -> str:
    if not isinstance(reader, ProductReader):
        return reader
    if reader.product not in plan.roles:
        raise DatapatchbayError(f"Reader product {reader.product!r} is not a data product folder in this repository.")
    return plan.roles[reader.product]


def _view_sql(table: TablePlan, pii_readers: Iterable[str]) -> str:
    is_pii_reader = " OR ".join(f"pg_has_role(current_user, {_literal(role)}, 'member')" for role in pii_readers)
    return view_sql(
        table,
        _DIALECT,
        lambda name: f"CASE WHEN {is_pii_reader or 'false'} THEN {name} ELSE NULL END AS {name}",
    )
