"""Writing and deleting the files `dpb generate` owns, whole or not at all."""

import contextlib
import os
from pathlib import Path

from datapatchbay.errors import GenerationError

__all__ = ["remove_file", "write_file"]


def write_file(destination: Path, content: str) -> None:
    """Write a file whole or not at all: to a temporary file next to it, then move it into place.

    Raises:
        GenerationError: If the file cannot be written.
    """
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(content.encode("utf-8"))
        os.replace(temporary, destination)
    except OSError as exc:
        with contextlib.suppress(OSError):  # best effort: the write error is the one to report
            temporary.unlink(missing_ok=True)
        raise GenerationError(f"cannot write {destination}: {exc.strerror or exc}") from exc


def remove_file(path: Path) -> None:
    """Delete a file.

    Raises:
        GenerationError: If the file cannot be deleted.
    """
    try:
        path.unlink()
    except OSError as exc:
        raise GenerationError(f"cannot delete {path}: {exc.strerror or exc}") from exc
