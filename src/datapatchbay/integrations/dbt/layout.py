"""The checks of the dbt executor: which tables dbt builds, and the models and files they need (ADR-0013, ADR-0015).

dbt is a build tool behind the executor seam. A table is built by dbt when its executor, resolved over the settings
cascade (ADR-0008), is `dbt`. Such a table keeps its contract in the table file and has no build code of its own: its
SQL is a dbt model in the `models/` folder of its data product, and dbt takes the order of the build from `ref()`.
Nothing here imports or runs dbt (ADR-0004).
"""

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from datapatchbay.files.repomodel import DataProduct, Repo, Table
from datapatchbay.integrations.dbt.settings import dbt_model_template, dbt_settings
from datapatchbay.plugins import NewTable, TablePlan
from datapatchbay.problems import Problem
from datapatchbay.settings.effective import EffectiveSettings
from datapatchbay.settings.naming import NamingTemplateError, derive_names, render_name

__all__ = [
    "DBT_EXECUTOR",
    "MODELS_FOLDER",
    "TESTS_FOLDER",
    "DbtLocation",
    "check_dbt_dataproduct",
    "check_dbt_table",
    "dbt_location",
    "model_name",
    "new_model_name",
]

DBT_EXECUTOR = "dbt"
"""The name of the dbt executor."""

MODELS_FOLDER = "models"
"""The folder of a data product that holds its dbt models."""

TESTS_FOLDER = "tests"
"""The folder of a data product that holds its generated singular dbt tests (ADR-0019)."""

_BUILD_KEYS = ("entrypoint", "params", "needs")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True, slots=True)
class DbtLocation:
    """Where dbt finds a data product's models, project and profile, as the `dbt` settings and the folders give it.

    Attributes:
        models: The `models/` folder of the data product, relative to the dbt project, for `dbt build --select`.
        project_dir: The dbt project on the worker: an absolute path as set, or the path from the data product folder
            to the project.
        profiles_dir: The folder with `profiles.yml` on the worker, as set.
    """

    models: PurePosixPath
    project_dir: str
    profiles_dir: str


def dbt_location(table: TablePlan) -> DbtLocation:
    """Place the models of a table's data product in the project that the `dbt:` settings block locates."""
    dbt = dbt_settings(table.plugin_settings)
    models = table.directory / MODELS_FOLDER
    if PurePosixPath(dbt.project_dir).is_absolute():
        # The project is a copy of the repo's layout somewhere else on the worker: select by the path in the repo.
        project_dir = dbt.project_dir
        select = os.path.relpath(models, table.root)
    else:
        project = Path(os.path.normpath(table.root / dbt.project_dir))
        project_dir = Path(os.path.relpath(project, table.directory)).as_posix()
        select = os.path.relpath(models, project)
    return DbtLocation(
        models=PurePosixPath(Path(select).as_posix()), project_dir=project_dir, profiles_dir=dbt.profiles_dir
    )


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
            dbt_model_template(conventions),
            name=dataproduct.file.model.name,
            kind_name=kind_name,
            kind=conventions.kinds[kind_name],
            extra={"dataproduct": derived.dataproduct, "table": table.name},
        )
    except NamingTemplateError:
        return None


def new_model_name(new: NewTable, table: str) -> str:
    """Return the dbt model name of a table of a data product `dpb new` is writing, from the `dbt_model` template."""
    conventions = new.conventions
    return render_name(
        dbt_model_template(conventions),
        name=new.dataproduct_name,
        kind_name=new.kind,
        kind=conventions.kinds[new.kind],
        extra={"dataproduct": new.dataproduct, "table": table},
    )


def check_dbt_dataproduct(repo: Repo, dataproduct: DataProduct) -> Iterator[Problem]:
    """Check what the folder of a dbt model must hold.

    - No `.py` file sits in the `models/` folder of a data product, because dbt reads it as a dbt Python model.

    Args:
        repo: The loaded repository.
        dataproduct: The data product to check.
    """
    return _check_models_folder(repo, dataproduct)


def check_dbt_table(
    settings: EffectiveSettings, dataproduct: DataProduct, table: Table, used: dict[str, PurePosixPath]
) -> Iterator[Problem]:
    """Check how a table built by dbt fits its table file.

    - It has no `entrypoint`, `params` or `needs`, and its model file exists.
    - The rendered model name is a plain identifier, and no other such table has the same name.

    Args:
        settings: The effective settings, which hold the naming templates.
        dataproduct: The data product that holds the table.
        table: The table dbt builds.
        used: Lower-cased model name -> table file, for the tables checked so far; the check adds this table.
    """
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
