"""Keeping the `model-paths` of the root `dbt_project.yml` in step with the data product folders (ADR-0015).

One dbt project spans the folders of several data products. dbt resolves `model-paths` relative to the folder of
`dbt_project.yml`, which sits at the repo root, so each entry is the `models/` folder of a data product relative to the
repo root. Only that key is changed.
"""

from pathlib import Path

from ruamel.yaml.comments import CommentedSeq

from datapatchbay.cascade import resolve_setting
from datapatchbay.dbt import DBT_EXECUTOR, MODELS_FOLDER
from datapatchbay.errors import DatapatchbayError
from datapatchbay.repomodel import Repo
from datapatchbay.settings import EffectiveSettings
from datapatchbay.yamlio import YamlLoadError, dump_mapping, load_mapping

DBT_PROJECT_FILE = "dbt_project.yml"
"""The name of the dbt project file, expected at the repo root."""

_KEY = "model-paths"


class DbtProjectError(DatapatchbayError):
    """Raised when tables are built by dbt but the root `dbt_project.yml` is missing or unreadable."""


def model_paths(repo: Repo, settings: EffectiveSettings) -> list[str]:
    """List the `models/` folder of every data product that has a table built by dbt.

    Returns:
        The folders relative to the repo root, in posix form, sorted.
    """
    paths = {
        (dataproduct.directory / MODELS_FOLDER).relative_to(repo.root).as_posix()
        for dataproduct in repo.dataproducts
        for port in dataproduct.ports
        for table in port.tables
        if resolve_setting("executor", settings, dataproduct=dataproduct, port=port, table=table).value == DBT_EXECUTOR
    }
    return sorted(paths)


def synced_dbt_project(repo: Repo, settings: EffectiveSettings) -> tuple[Path, str] | None:
    """Work out the new text of the root `dbt_project.yml`, without writing it.

    Returns:
        The path and the new text, or `None` when no table is built by dbt or the file is already in step.

    Raises:
        DbtProjectError: If tables are built by dbt and the root `dbt_project.yml` is missing or not a YAML mapping.
    """
    wanted = model_paths(repo, settings)
    if not wanted:
        return None
    path = repo.root / DBT_PROJECT_FILE
    if not path.is_file():
        raise DbtProjectError(
            f"tables are built by dbt, so a {DBT_PROJECT_FILE} is expected at the repo root ({path}); "
            "create it, for example with `name`, `version` and `profile`"
        )
    try:
        data = load_mapping(path)
    except YamlLoadError as exc:
        raise DbtProjectError(f"{path}: {exc}") from exc
    current = data.get(_KEY)
    if isinstance(current, CommentedSeq):
        if list(current) == wanted:
            return None
        current[:] = wanted  # in place, so the comments and the flow or block style of the list stay
    else:
        data[_KEY] = wanted
    return path, dump_mapping(data)
