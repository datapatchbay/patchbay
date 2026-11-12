"""The checks of the dbt executor: which tables dbt builds, and the models and files they need (ADR-0013, ADR-0015).

dbt is a build tool behind the executor seam. A table is built by dbt when its executor, resolved over the settings
cascade (ADR-0008), is `dbt`. Such a table keeps its contract in the table file and has no build code of its own: its
SQL is a dbt model in the `models/` folder of its data product, and dbt takes the order of the build from `ref()`.
Nothing here imports or runs dbt (ADR-0004).
"""

import re
from collections.abc import Iterator
from pathlib import PurePosixPath

from datapatchbay.cascade import ResolvedCascade
from datapatchbay.naming import NamingTemplateError, derive_names, render_name
from datapatchbay.problems import Problem
from datapatchbay.repomodel import DataProduct, Repo, Table
from datapatchbay.settings import EffectiveSettings

DBT_EXECUTOR = "dbt"
"""The name of the dbt executor."""

MODELS_FOLDER = "models"
"""The folder of a data product that holds its dbt models."""

TESTS_FOLDER = "tests"
"""The folder of a data product that holds its generated singular dbt tests (ADR-0019)."""

_BUILD_KEYS = ("entrypoint", "params", "needs")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def model_name(settings: EffectiveSettings, dataproduct: DataProduct, table: Table) -> str | None:
    """Return the dbt model name of a table, rendered from the `dbt_model` naming template.

    The name is also the file name of the model, `models/<name>.sql`, in the data product folder.

    Args:
        settings: The effective settings, which hold the naming templates and kinds.
        dataproduct: The data product that holds the table.
        table: The table the model builds.

    Returns:
        The name, or `None` when the template or the data product's kind is invalid, which other checks report.
    """
    conventions = settings.values.conventions
    kind_name = dataproduct.file.model.kind
    if kind_name not in conventions.kinds:
        return None
    try:
        derived = derive_names(conventions, name=dataproduct.file.model.name, kind_name=kind_name)
        return render_name(
            conventions.names.dbt_model,
            name=dataproduct.file.model.name,
            kind_name=kind_name,
            kind=conventions.kinds[kind_name],
            extra={"dataproduct": derived.dataproduct, "table": table.name},
        )
    except NamingTemplateError:
        return None


def check_dbt(repo: Repo, settings: EffectiveSettings, cascade: ResolvedCascade) -> list[Problem]:
    """Check how the executor of each table fits its table file, and what the folder of a dbt model must hold.

    - A table built by dbt has no `entrypoint`, `params` or `needs`, and its model file exists.
    - The rendered model name of a table built by dbt is a plain identifier, and no other such table has the same name.
    - Any other table needs a `build.entrypoint`, because the python executor calls it.
    - No `.py` file sits in the `models/` folder of a data product, because dbt reads it as a dbt Python model.

    Args:
        repo: The loaded repository.
        settings: The effective settings, which hold the naming templates.
        cascade: The resolved settings, which give the executor of each table.

    Returns:
        The problems found, empty when the executors fit the table files.
    """
    problems: list[Problem] = []
    # Lower-cased model name -> table file: model names are unique in a dbt project, and a warehouse folds case.
    used: dict[str, PurePosixPath] = {}
    for dataproduct in repo.dataproducts:
        problems.extend(_check_models_folder(repo, dataproduct))
        for port in dataproduct.ports:
            for table in port.tables:
                executor = cascade.for_table(table)["executor"]
                if executor.value == DBT_EXECUTOR:
                    problems.extend(_check_dbt_table(settings, dataproduct, table, used))
                else:
                    problems.extend(_check_entrypoint(table, executor.value))
    return problems


def _check_dbt_table(
    settings: EffectiveSettings, dataproduct: DataProduct, table: Table, used: dict[str, PurePosixPath]
) -> Iterator[Problem]:
    file = table.file
    build = file.model.build
    if build is not None:
        for key in _BUILD_KEYS:
            if key in build.model_fields_set:
                yield Problem(
                    file.path,
                    file.line("build", key),
                    f"`build.{key}` is not allowed on table '{table.name}', which dbt builds; "
                    "dbt takes the order from `ref()` in the model",
                )
    name = model_name(settings, dataproduct, table)
    if name is not None and not _IDENTIFIER.fullmatch(name):
        yield Problem(
            file.path,
            file.line("name"),
            f"dbt model name '{name}' of table '{table.name}', rendered from `conventions.names.dbt_model`, is not "
            "a plain identifier; use letters, digits and underscores, not starting with a digit",
        )
    elif name is not None and name.lower() in used:
        yield Problem(
            file.path,
            file.line("name"),
            f"dbt model name '{name}' is already used by {used[name.lower()]}; dbt model names are unique across the "
            "repo, whatever their case, so include `{dataproduct}` in `conventions.names.dbt_model`",
        )
    elif name is not None:
        used[name.lower()] = file.path
    if (
        name is not None
        and _IDENTIFIER.fullmatch(name)
        and not (dataproduct.directory / MODELS_FOLDER / f"{name}.sql").is_file()
    ):
        yield Problem(
            file.path,
            file.line("name"),
            f"model file {MODELS_FOLDER}/{name}.sql does not exist in the folder of data product "
            f"'{dataproduct.folder}'; table '{table.name}' is built by dbt",
        )


def _check_entrypoint(table: Table, executor: object) -> Iterator[Problem]:
    file = table.file
    build = file.model.build
    if build is None:
        yield Problem(
            file.path,
            None,
            f"table '{table.name}' needs a `build` block with an `entrypoint`, because its executor is '{executor}'",
        )
    elif build.entrypoint is None:
        yield Problem(
            file.path,
            file.line("build"),
            f"table '{table.name}' needs a `build.entrypoint`, because its executor is '{executor}'",
        )


def _check_models_folder(repo: Repo, dataproduct: DataProduct) -> Iterator[Problem]:
    models = dataproduct.directory / MODELS_FOLDER
    if not models.is_dir():
        return
    for path in sorted(models.rglob("*.py")):
        yield Problem(
            PurePosixPath(path.relative_to(repo.root).as_posix()),
            None,
            f"a .py file in a data product's `{MODELS_FOLDER}/` folder is read by dbt as a dbt Python model; "
            "move it to `src/`",
        )
