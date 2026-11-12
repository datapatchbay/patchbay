"""Keeping the `model-paths` and `test-paths` of the root `dbt_project.yml` in step with the data product folders.

One dbt project spans the folders of several data products. dbt resolves `model-paths` relative to the folder of
`dbt_project.yml`, which sits at the repo root, so each entry is the `models/` folder of a data product relative to the
repo root, and the same for the `tests/` folders in `test-paths` (ADR-0015, ADR-0019). Only those keys are changed.
"""

from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from ruamel.yaml.comments import CommentedSeq

from datapatchbay.dbt import MODELS_FOLDER, TESTS_FOLDER
from datapatchbay.errors import DatapatchbayError
from datapatchbay.repo import DATAPRODUCTS_DIR
from datapatchbay.yamlio import YamlLoadError, dump_mapping, load_mapping

DBT_PROJECT_FILE = "dbt_project.yml"
"""The name of the dbt project file, expected at the repo root."""

_MODEL_KEY = "model-paths"
_TEST_KEY = "test-paths"


class DbtProjectError(DatapatchbayError):
    """Raised when tables are built by dbt but the root `dbt_project.yml` is missing or unreadable."""


def synced_dbt_project(root: Path, model_paths: Sequence[str], test_paths: Sequence[str]) -> tuple[Path, str] | None:
    """Work out the new text of the root `dbt_project.yml`, without writing it.

    Once any table is built by dbt, `model-paths` and `test-paths` are owned by `dpb generate`: they are
    replaced, not merged, so a hand-set entry is lost. When no table is built by dbt any more, only the entries that
    point at the `models/` or `tests/` folder of a data product are removed (a key too when none is left), and
    nothing else is touched.

    Args:
        root: The repo root, where `dbt_project.yml` is expected.
        model_paths: The `models/` folder of every data product with a table built by dbt, relative to the root.
        test_paths: The `tests/` folder of those data products.

    Returns:
        The path and the new text, or `None` when the file is already in step, or missing or unreadable while no
        table is built by dbt.

    Raises:
        DbtProjectError: If tables are built by dbt and the root `dbt_project.yml` is missing or not a YAML mapping.
    """
    wanted = {_MODEL_KEY: list(model_paths), _TEST_KEY: list(test_paths)}
    path = root / DBT_PROJECT_FILE
    if not wanted[_MODEL_KEY]:
        return _without_stale_paths(path)
    if not path.is_file():
        raise DbtProjectError(
            f"tables are built by dbt, so a {DBT_PROJECT_FILE} is expected at the repo root ({path}); "
            "create it, for example with `name`, `version` and `profile`"
        )
    try:
        data = load_mapping(path)
    except YamlLoadError as exc:
        raise DbtProjectError(f"{path}: {exc}") from exc
    changed = False
    for key, folders in wanted.items():
        current = data.get(key)
        if isinstance(current, CommentedSeq):
            if list(current) != folders:
                current[:] = folders  # in place, so the comments and the flow or block style of the list stay
                changed = True
        else:
            data[key] = folders
            changed = True
    return (path, dump_mapping(data)) if changed else None


def _is_data_product_folder(entry: object) -> bool:
    if not isinstance(entry, str):
        return False
    parts = PurePosixPath(entry).parts
    return len(parts) == 3 and parts[0] == DATAPRODUCTS_DIR and parts[2] in (MODELS_FOLDER, TESTS_FOLDER)


def _without_stale_paths(path: Path) -> tuple[Path, str] | None:
    """No table is built by dbt: drop the `model-paths` and `test-paths` entries `dpb generate` once wrote."""
    if not path.is_file():
        return None
    try:
        data = load_mapping(path)
    except YamlLoadError:
        return None  # dbt is not used, so a project file that is not ours to read is not a problem
    changed = False
    for key in (_MODEL_KEY, _TEST_KEY):
        current = data.get(key)
        if not isinstance(current, CommentedSeq) or not any(_is_data_product_folder(entry) for entry in current):
            continue
        kept = [entry for entry in current if not _is_data_product_folder(entry)]
        if kept:
            current[:] = kept
        else:
            del data[key]
        changed = True
    return (path, dump_mapping(data)) if changed else None
