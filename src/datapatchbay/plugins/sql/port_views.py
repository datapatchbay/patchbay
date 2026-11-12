"""What the views of an output port have in common on every built-in warehouse (ADR-0002).

An output port is a schema that holds one view per table, over the table in the private schema. What differs between
warehouses is how a PII column is masked and how access is granted; the ports, their tables and the view itself are
the same.
"""

from collections.abc import Callable, Iterator, Sequence

from datapatchbay.plugins import DataProductPlan, TablePlan
from datapatchbay.plugins.sql.audit_sql import Dialect
from datapatchbay.repomodel import Port


def output_ports(plan: DataProductPlan) -> Iterator[tuple[Port, Sequence[TablePlan]]]:
    """Yield each output port of the data product with the tables that are in it."""
    for port in plan.source.outputs:
        if port.name in plan.outputs:
            yield port, [table for table in plan.tables if table.port == port.name]


def view_sql(table: TablePlan, dialect: Dialect, pii_column: Callable[[str], str]) -> str:
    """Return the statement that creates the table's view in its port's schema.

    The view lists the columns of the table file, in order. `pii_column` turns the quoted name of a PII column into
    the expression that the view selects for it.
    """
    columns = []
    for column in table.source.file.model.columns:
        name = dialect.identifier(column.name)
        columns.append(pii_column(name) if column.pii else name)
    private = f"{dialect.identifier(table.schema)}.{dialect.identifier(table.name)}"
    view = f"{dialect.identifier(table.port)}.{dialect.identifier(table.name)}"
    return f"CREATE VIEW {view} AS SELECT {', '.join(columns) or '*'} FROM {private};"
