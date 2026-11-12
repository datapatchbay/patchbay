"""The problem and report types that every validation step produces."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any


@dataclass(frozen=True, slots=True)
class Problem:
    """One thing wrong in one file.

    Attributes:
        file: The file, relative to the repo root and written with forward slashes.
        line: The 1-based line the problem points at, or `None` when the file has no usable position.
        message: What is wrong, in a sentence a user can act on.
    """

    file: PurePosixPath
    line: int | None
    message: str

    def render(self) -> str:
        """Format the problem as one `file:line: message` line."""
        location = f"{self.file}:{self.line}" if self.line is not None else str(self.file)
        return f"{location}: {self.message}"

    def to_json(self) -> dict[str, Any]:
        """Return the problem in the public `--json` shape."""
        return {"file": str(self.file), "line": self.line, "message": self.message}


@dataclass(frozen=True, slots=True)
class Report:
    """The result of validating a repo: how many data products were checked and what was wrong."""

    dataproducts_checked: int
    problems: Sequence[Problem]

    @property
    def ok(self) -> bool:
        """Whether validation found no problems."""
        return not self.problems

    def to_json(self) -> dict[str, Any]:
        """Return the report in the public `--json` shape."""
        return {
            "ok": self.ok,
            "dataproducts_checked": self.dataproducts_checked,
            "problems": [problem.to_json() for problem in self.problems],
        }
