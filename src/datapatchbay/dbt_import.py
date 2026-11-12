"""Reading the models and properties of an existing dbt project into a new data product (`dpb new --from-dbt`).

This is the inverse of `dbt_properties`: what that module writes from a table file, this one reads back into the
shape of a table file, with the same severity table. The dbt syntax variants of the properties are accepted:
`data_tests:` and the older `tests:`, test arguments under `arguments:` (dbt 1.10.5 and later) or directly under the
test, `severity` under `config:` or directly under the test, and the `name:` plus `test_name:` form.

A data test is imported only when it maps to a quality rule without changing what it checks. Every other one is
reported, never dropped silently. Nothing here imports or runs dbt (ADR-0004).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from datapatchbay.dbt_properties import SEVERITY
from datapatchbay.errors import DatapatchbayError
from datapatchbay.genheader import generated_from
from datapatchbay.naming import is_snake_case
from datapatchbay.yamlio import YamlLoadError, load_mapping

DEFAULT_TYPE = "text"
"""The column type written when the dbt properties give no `data_type`."""

_DBT_SEVERITY = {dbt: rule for rule, dbt in SEVERITY.items()}
_BUILT_IN = ("not_null", "unique", "accepted_values")
_HARMLESS = {"name", "tags", "meta", "description"}
_ARGUMENTS = {"accepted_values": {"values", "quote"}, "not_null": set(), "unique": set()}
_QUOTED_SQL = re.compile(r"'((?:[^']|'')*)'")


class DbtImportError(DatapatchbayError):
    """Raised when a dbt project cannot be read: a missing folder, or models that cannot become tables."""


@dataclass(frozen=True, slots=True)
class ImportedModel:
    """One dbt model, ready to become a table file and a model file.

    Attributes:
        name: The model's name in the dbt project; it becomes the name of the table.
        sql: The model's SQL as written.
        description: The model's description, or `None`.
        columns: The columns as the table file writes them: name, type, description, pii and rules.
    """

    name: str
    sql: str
    description: str | None
    columns: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class UnmappedTest:
    """A data test with no matching quality rule: `column` is `None` for a test on the model."""

    model: str
    column: str | None
    test: str
    reason: str


@dataclass(frozen=True, slots=True)
class Skipped:
    """A model that was not imported, with the reason."""

    model: str
    reason: str


@dataclass(frozen=True, slots=True)
class UntypedColumn:
    """A column whose properties gave no `data_type`; it is written with `DEFAULT_TYPE`."""

    model: str
    column: str


@dataclass(slots=True)
class DbtImport:
    """What was read from a dbt project: the models to import, and everything that was left out."""

    models: list[ImportedModel] = field(default_factory=list)
    unmapped: list[UnmappedTest] = field(default_factory=list)
    skipped: list[Skipped] = field(default_factory=list)
    untyped: list[UntypedColumn] = field(default_factory=list)


def read_dbt_models(path: Path, *, default_severity: str = "error") -> DbtImport:
    """Read the models (`.sql`) and their properties (`.yml`, `.yaml`) below a folder.

    Args:
        path: The folder with the dbt models and properties; subfolders are read too.
        default_severity: The severity the new repo gives a rule without one. A dbt test without a severity fails the
            build, so it is `error`; the rule is written with an explicit severity when the default differs.

    Returns:
        The models that have both a SQL file and properties with at least one column, sorted by name.

    Raises:
        DbtImportError: If the folder is missing, a model is declared twice or has two SQL files, or a model name is
            not snake_case.
    """
    if not path.is_dir():
        raise DbtImportError(f"--from-dbt: {path} is not a folder")
    sql_files = _sql_files(path)
    declared = _declared_models(path)
    result = DbtImport()
    for name in sorted({*sql_files, *declared}):
        if name not in sql_files:
            result.skipped.append(Skipped(name, "its properties have no .sql file"))
        elif name not in declared:
            result.skipped.append(Skipped(name, "it has no properties, so there are no columns for a table file"))
        elif not isinstance(declared[name].get("columns"), CommentedSeq) or not declared[name]["columns"]:
            result.skipped.append(Skipped(name, "its properties list no columns, which a table file needs"))
        else:
            result.models.append(_import_model(name, sql_files[name], declared[name], default_severity, result))
    bad = [model.name for model in result.models if not is_snake_case(model.name)]
    if bad:
        raise DbtImportError(f"model name(s) {', '.join(bad)} must be snake_case to become table names; rename them")
    return result


def _sql_files(path: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for file in sorted(path.rglob("*.sql")):
        if generated_from(file) is not None:
            continue
        if file.stem in found:
            raise DbtImportError(f"model '{file.stem}' has two .sql files: {found[file.stem]} and {file}")
        found[file.stem] = file
    return found


def _declared_models(path: Path) -> dict[str, CommentedMap]:
    declared: dict[str, CommentedMap] = {}
    for file in sorted([*path.rglob("*.yml"), *path.rglob("*.yaml")]):
        if generated_from(file) is not None:
            continue
        try:
            data = load_mapping(file)
        except YamlLoadError:
            continue  # not a properties file; dbt reports its own files
        entries = data.get("models")
        if not isinstance(entries, CommentedSeq):
            continue
        for entry in entries:
            name = entry.get("name") if isinstance(entry, CommentedMap) else None
            if not isinstance(name, str):
                continue
            if name in declared:
                raise DbtImportError(f"model '{name}' is declared more than once in the properties below {path}")
            declared[name] = entry
    return declared


def _import_model(name: str, sql: Path, entry: CommentedMap, default: str, result: DbtImport) -> ImportedModel:
    columns = []
    for raw in entry["columns"]:
        if not isinstance(raw, CommentedMap) or not isinstance(raw.get("name"), str):
            continue
        column: dict[str, Any] = {"name": raw["name"]}
        data_type = raw.get("data_type")
        if isinstance(data_type, str) and data_type:
            column["type"] = data_type
        else:
            column["type"] = DEFAULT_TYPE
            result.untyped.append(UntypedColumn(name, raw["name"]))
        if isinstance(raw.get("description"), str):
            column["description"] = raw["description"]
        if _is_pii(raw):
            column["pii"] = True
        rules = [
            rule for test in _tests(raw) if (rule := _map_test(test, name, raw["name"], default, result)) is not None
        ]
        if rules:
            column["rules"] = rules
        columns.append(column)
    for test in _tests(entry):
        label = _test_name(test)
        result.unmapped.append(
            UnmappedTest(name, None, label, "a data test on the whole model has no matching quality rule")
        )
    description = entry.get("description")
    return ImportedModel(
        name, sql.read_text(encoding="utf-8"), description if isinstance(description, str) else None, columns
    )


def _is_pii(column: Mapping[str, Any]) -> bool:
    for holder in (column, column.get("config")):
        meta = holder.get("meta") if isinstance(holder, Mapping) else None
        if isinstance(meta, Mapping) and meta.get("pii") is True:
            return True
    return False


def _tests(entry: Mapping[str, Any]) -> list[Any]:
    """The data tests of a model or column, under `data_tests:` or the older `tests:`."""
    found: list[Any] = []
    for key in ("data_tests", "tests"):
        value = entry.get(key)
        if isinstance(value, list):
            found.extend(value)
    return found


def _split(test: Any) -> tuple[str, dict[str, Any]]:
    """The test's name and its settings, merged: top-level keys, `arguments:` and `config:`."""
    if isinstance(test, str):
        return test, {}
    if isinstance(test, Mapping) and "test_name" in test:
        return str(test["test_name"]), _merge(test)
    if isinstance(test, Mapping) and len(test) == 1:
        ((name, body),) = test.items()
        return str(name), _merge(body) if isinstance(body, Mapping) else {}
    return "<unrecognised>", {"": None}


def _merge(body: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {key: value for key, value in body.items() if key not in {"arguments", "config"}}
    for nested in ("arguments", "config"):
        value = body.get(nested)
        if isinstance(value, Mapping):
            merged.update(value)
    return merged


def _test_name(test: Any) -> str:
    return _split(test)[0]


def _map_test(test: Any, model: str, column: str, default: str, result: DbtImport) -> dict[str, Any] | str | None:
    name, settings = _split(test)

    def unmapped(reason: str) -> None:
        result.unmapped.append(UnmappedTest(model, column, name, reason))

    if name not in _BUILT_IN:
        unmapped("no matching quality rule")
        return None
    options = {key for key in settings if key not in _HARMLESS | _ARGUMENTS[name] | {"severity"}}
    if options:
        unmapped(f"option(s) {', '.join(f'`{o}`' for o in sorted(options))} have no equivalent in a quality rule")
        return None
    dbt_severity = settings.get("severity", "error")
    severity = _DBT_SEVERITY.get(dbt_severity.lower()) if isinstance(dbt_severity, str) else None
    if severity is None:
        unmapped(f"severity {dbt_severity!r} is not 'error' or 'warn'")
        return None
    rule: dict[str, Any] = {"rule": name}
    if severity != default:
        rule["severity"] = severity
    if name == "accepted_values":
        values = _accepted_values(settings)
        if isinstance(values, str):
            unmapped(values)
            return None
        rule["values"] = values
    return rule["rule"] if len(rule) == 1 else rule


def _accepted_values(settings: Mapping[str, Any]) -> list[str | int | float | bool] | str:
    """The values as the rule holds them, or the reason that they cannot be."""
    values = settings.get("values")
    quote = settings.get("quote", True)
    if not isinstance(values, list) or not values or not isinstance(quote, bool):
        return "`values` is not a list of literal values, or `quote` is not true or false"
    mapped: list[str | int | float | bool] = []
    for value in values:
        if not isinstance(value, str | int | float):
            return "`values` holds something that is not a literal"
        if quote:
            mapped.append(str(value))  # dbt quotes every value, so a number is the text of that number
        elif isinstance(value, str):
            match = _QUOTED_SQL.fullmatch(value)
            if match is None:
                return f"value {value} is SQL that is not a quoted string, which a quality rule cannot hold"
            mapped.append(match.group(1).replace("''", "'"))
        else:
            mapped.append(value)
    return mapped


def rename_refs(sql: str, names: Mapping[str, str]) -> str:
    """Rewrite `ref('old')` to `ref('new')` for the models that moved, keeping the quotes as written."""

    def replace(match: re.Match[str]) -> str:
        old = match.group("name")
        return f"{match.group('head')}{names.get(old, old)}{match.group('quote')}{match.group('tail')}"

    return re.sub(r"(?P<head>\bref\(\s*(?P<quote>['\"]))(?P<name>[^'\"]+)(?P=quote)(?P<tail>\s*\))", replace, sql)
