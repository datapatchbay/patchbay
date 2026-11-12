"""Finding the repo root and the files inside it."""

from pathlib import Path

from datapatchbay.errors import RepoNotFoundError

ROOT_FILE = "datapatchbay.yaml"
DATAPRODUCTS_DIR = "dataproducts"
DATAPRODUCT_FILE = "dataproduct.yaml"


def find_repo_root(start: Path) -> Path:
    """Find the repo root: the nearest directory at or above `start` that holds `datapatchbay.yaml`.

    Args:
        start: The directory to begin the search in, usually the working directory.

    Returns:
        The absolute path of the repo root.

    Raises:
        RepoNotFoundError: If no directory up to the file system root holds `datapatchbay.yaml`.
    """
    start = start.resolve()
    for directory in (start, *start.parents):
        if (directory / ROOT_FILE).is_file():
            return directory
    raise RepoNotFoundError(f"no {ROOT_FILE} found in {start} or any parent directory; is this a datapatchbay repo?")


def find_dataproduct_files(root: Path) -> list[Path]:
    """List every `dataproduct.yaml` under `dataproducts/`, sorted so output is deterministic."""
    return sorted((root / DATAPRODUCTS_DIR).rglob(DATAPRODUCT_FILE))
