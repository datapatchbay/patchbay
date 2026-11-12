"""The singular dbt data tests of the table rules of tables that dbt builds, generated from the table files (ADR-0019).

`primary_key`, `row_count` and `sql` have no built-in dbt test, so each becomes one SQL file in the `tests/` folder of
the data product. The SQL selects the rows that break the rule, so the test passes when it returns none. The rules
judge the same way as the audit queries of the Postgres warehouse: a null in a key column breaks a primary key, a
repeated key breaks it, and a null is never counted as repeated. The files are committed, so the output is
deterministic. Nothing here imports or runs dbt (ADR-0004), and the files need no dbt package.
"""

from collections import Counter
from collections.abc import Sequence

from datapatchbay.genheader import generated_header
from datapatchbay.integrations.dbt.layout import DBT_EXECUTOR, TESTS_FOLDER, model_name
from datapatchbay.models.table import PrimaryKeyRule, RowCountRule, SqlRule, TableRule
from datapatchbay.plugins import DataProductPlan, GeneratedFile, TablePlan
from datapatchbay.settings import EffectiveSettings

_SEVERITY = {"error": "error", "warning": "warn"}


def generate_dbt_tests(plans: Sequence[DataProductPlan], settings: EffectiveSettings) -> list[GeneratedFile]:
    """Generate the singular dbt tests of the table rules of every table built by dbt.

    Args:
        plans: The plans of a valid repo.
        settings: The effective settings, which hold the `dbt_model` naming template.

    Returns:
        The files, with paths relative to the repo root, sorted by path. Empty when no such table has a table rule
        that is not ignored.
    """
    files: list[GeneratedFile] = []
    for plan in plans:
        tests = plan.source.file.path.parent / TESTS_FOLDER
        for table in plan.tables:
            if table.executor != DBT_EXECUTOR:
                continue
            model = model_name(settings, plan.source, table.source)
            if model is None:
                raise RuntimeError(f"table '{table.name}' is built by dbt but has no model name; validation missed it")
            seen: Counter[str] = Counter()
            for rule in table.source.file.model.rules:
                seen[rule.rule] += 1
                severity = table.severity_of(rule.severity)
                if severity == "none":
                    continue  # still counted above, so that another rule keeps its file name
                suffix = "" if seen[rule.rule] == 1 else f"_{seen[rule.rule]}"
                content = (
                    _header(table) + f"{{{{ config(severity='{_SEVERITY[severity]}') }}}}\n\n" + _select(rule, model)
                )
                files.append(GeneratedFile(tests / f"{model}__{rule.rule}{suffix}.sql", content))
    return sorted(files, key=lambda file: file.path)


def _header(table: TablePlan) -> str:
    return generated_header(table.source.file.path, comment="--")


def _select(rule: TableRule, model: str) -> str:
    match rule:
        case PrimaryKeyRule():
            return _primary_key(rule, model)
        case RowCountRule():
            return _row_count(rule, model)
        case SqlRule():
            # dbt wraps a test in a subquery, which a trailing semicolon would break
            return rule.sql.strip().rstrip(";").rstrip() + "\n"


def _primary_key(rule: PrimaryKeyRule, model: str) -> str:
    names = [f"{{{{ adapter.quote({_jinja_string(column)}) }}}}" for column in rule.columns]
    selected = "".join(f"    {name},\n" for name in names)
    any_null = " or ".join(f"{name} is null" for name in names)
    return (
        f"select\n{selected}    count(*) as occurrences\n"
        f"from {_ref(model)}\n"
        f"group by {', '.join(names)}\n"
        f"having {any_null} or count(*) > 1\n"
    )


def _row_count(rule: RowCountRule, model: str) -> str:
    bounds = []
    if rule.min is not None:
        bounds.append(f"n < {rule.min}")
    if rule.max is not None:
        bounds.append(f"n > {rule.max}")
    return f"select n\nfrom (select count(*) as n from {_ref(model)}) as counted\nwhere {' or '.join(bounds)}\n"


def _ref(model: str) -> str:
    return f"{{{{ ref({_jinja_string(model)}) }}}}"


def _jinja_string(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"
