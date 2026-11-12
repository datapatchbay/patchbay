"""Quoting of names and values in generated SQL, the standard way that Postgres and DuckDB both read."""


def standard_identifier(name: str) -> str:
    """Quote a schema, table, column or role name."""
    return '"' + name.replace('"', '""') + '"'


def standard_literal(value: str | int | float | bool) -> str:
    """Write a value: a string between single quotes, a boolean as TRUE or FALSE, a number as it is."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return repr(value)
