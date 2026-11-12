"""The model of a table file: the contract (columns, quality rules) and the build."""

import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    GetJsonSchemaHandler,
    Tag,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, PydanticCustomError

from datapatchbay.models.base import FileModel

Severity = Literal["error", "warning", "none"]
COLUMN_RULES = ("not_null", "unique", "accepted_values")
TABLE_RULES = ("primary_key", "row_count", "sql")

_ENTRYPOINT = re.compile(r"[^:\s]+\.py:[A-Za-z_][A-Za-z0-9_]*")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Rule(_Strict):
    """Shared by every quality rule. A bare rule name in the YAML is the short form."""

    severity: Severity | None = Field(
        default=None,
        description="What happens when the rule is broken: `error` fails the run, `warning` reports and continues, "
        "`none` ignores the rule. Omitted means the default severity from the settings.",
    )

    @model_validator(mode="before")
    @classmethod
    def _expand_short_form(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"rule": data}
        return data


class NotNullRule(_Rule):
    """Every value in the column is present."""

    rule: Literal["not_null"] = Field(description="The rule name.")


class UniqueRule(_Rule):
    """No value occurs twice in the column."""

    rule: Literal["unique"] = Field(description="The rule name.")


class AcceptedValuesRule(_Rule):
    """The column only holds values from a fixed list."""

    rule: Literal["accepted_values"] = Field(description="The rule name.")
    values: list[str | int | float | bool] = Field(min_length=1, description="The values the column may hold.")


class PrimaryKeyRule(_Rule):
    """The columns together identify a row: never null and never repeated."""

    rule: Literal["primary_key"] = Field(description="The rule name.")
    columns: list[str] = Field(min_length=1, description="Names of the columns that form the primary key.")


class RowCountRule(_Rule):
    """The table holds a number of rows within bounds."""

    rule: Literal["row_count"] = Field(description="The rule name.")
    min: int | None = Field(default=None, ge=0, description="Fewest rows the table may hold.")
    max: int | None = Field(default=None, ge=0, description="Most rows the table may hold.")

    @model_validator(mode="after")
    def _check_bounds(self) -> "RowCountRule":
        if self.min is None and self.max is None:
            raise PydanticCustomError("row_count_bounds", "row_count needs `min`, `max` or both")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise PydanticCustomError("row_count_bounds", "row_count `min` is larger than `max`")
        return self


class SqlRule(_Rule):
    """A custom check: the SQL selects the rows that break the rule, so the rule holds when it returns none."""

    rule: Literal["sql"] = Field(description="The rule name.")
    sql: str = Field(min_length=1, description="A SELECT statement that returns the rows that break the rule.")


def _rule_tag(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        name = value.get("rule")
        return name if isinstance(name, str) else None
    return None


class _ShortFormSchema:
    """Make the JSON Schema accept the bare rule name that `_Rule._expand_short_form` accepts.

    Only rules without required keys of their own can be written bare, so only those names are listed.
    """

    def __init__(self, *names: str) -> None:
        self._names = names

    def __get_pydantic_json_schema__(self, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        long_form = handler(core_schema)
        return {"anyOf": [long_form, {"type": "string", "enum": list(self._names)}]}


def _rule_union(rules: tuple[str, ...]) -> str:
    return ", ".join(f"'{rule}'" for rule in rules)


type ColumnRule = Annotated[
    Annotated[NotNullRule, Tag("not_null")]
    | Annotated[UniqueRule, Tag("unique")]
    | Annotated[AcceptedValuesRule, Tag("accepted_values")],
    Discriminator(
        _rule_tag,
        custom_error_type="unknown_rule",
        custom_error_message=f"unknown column rule; expected one of {_rule_union(COLUMN_RULES)}",
    ),
    _ShortFormSchema("not_null", "unique"),
]
type TableRule = Annotated[
    Annotated[PrimaryKeyRule, Tag("primary_key")]
    | Annotated[RowCountRule, Tag("row_count")]
    | Annotated[SqlRule, Tag("sql")],
    Discriminator(
        _rule_tag,
        custom_error_type="unknown_rule",
        custom_error_message=f"unknown table rule; expected one of {_rule_union(TABLE_RULES)}",
    ),
]


class Column(_Strict):
    """One column of a table."""

    name: str = Field(min_length=1, description="Name of the column.")
    type: str = Field(min_length=1, description="Column type as the warehouse spells it. Free text, not validated.")
    description: str | None = Field(default=None, description="What the column holds.")
    pii: bool = Field(
        default=False,
        description="Whether the column holds personal data. Only PII readers of the output port see its values.",
    )
    rules: list[ColumnRule] = Field(
        default_factory=list,
        description="Quality rules on this column: `not_null`, `unique` or `accepted_values`. "
        "A bare rule name is the short form; the long form is a mapping with `rule` and `severity`.",
    )


class Build(_Strict):
    """How the table is made (ADR-0003)."""

    executor: Literal["python"] = Field(description="The technology that builds the table. Only `python` for now.")
    entrypoint: str = Field(
        description="The function that builds the table, as `path/to/file.py:function`. The path is relative to "
        "the data product folder.",
        json_schema_extra={"pattern": r"^[^:\s]+\.py:[A-Za-z_][A-Za-z0-9_]*$"},
        examples=["src/orders.py:build"],
    )
    params: dict[str, Any] = Field(default_factory=dict, description="Parameters passed to the function.")
    needs: list[str] = Field(
        default_factory=list,
        description="Names of the tables of the same data product that must be built first.",
    )

    @field_validator("entrypoint")
    @classmethod
    def _check_entrypoint(cls, value: str) -> str:
        if not _ENTRYPOINT.fullmatch(value):
            raise ValueError(f"'{value}' is not an entrypoint; write it as path/to/file.py:function")
        return value


class TableFile(FileModel):
    """A table: the contract (columns and quality rules) and the build."""

    name: str = Field(min_length=1, description="Name of the table, unique within its data product.")
    description: str | None = Field(default=None, description="What one row of the table is.")
    columns: list[Column] = Field(min_length=1, description="The columns of the table.")
    freshness_column: str | None = Field(
        default=None,
        description="The column that holds the time of the newest data. Must be one of the columns.",
    )
    rules: list[TableRule] = Field(
        default_factory=list,
        description="Quality rules on the table as a whole: `primary_key`, `row_count` or `sql`.",
    )
    build: Build = Field(description="How the table is made.")

    @field_validator("columns")
    @classmethod
    def _unique_column_names(cls, columns: list[Column]) -> list[Column]:
        seen: set[str] = set()
        for column in columns:
            if column.name in seen:
                raise ValueError(f"column '{column.name}' is declared more than once")
            seen.add(column.name)
        return columns

    @field_validator("freshness_column")
    @classmethod
    def _freshness_column_exists(cls, value: str | None, info: ValidationInfo) -> str | None:
        columns: list[Column] | None = info.data.get("columns")
        if value is not None and columns is not None and value not in {column.name for column in columns}:
            raise ValueError(f"'{value}' is not a column of this table")
        return value

    @field_validator("rules")
    @classmethod
    def _primary_key_columns_exist(cls, rules: list[TableRule], info: ValidationInfo) -> list[TableRule]:
        columns: list[Column] | None = info.data.get("columns")
        if columns is None:
            return rules
        names = {column.name for column in columns}
        for rule in rules:
            if isinstance(rule, PrimaryKeyRule):
                missing = [f"'{column}'" for column in rule.columns if column not in names]
                if missing:
                    raise ValueError(f"primary_key names unknown column(s) {', '.join(missing)}")
        return rules
