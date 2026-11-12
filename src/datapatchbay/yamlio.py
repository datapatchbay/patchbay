"""Reading YAML with line information, so every problem can name the line it came from."""

from collections.abc import Sequence
from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError


class YamlLoadError(Exception):
    """A file could not be read as a YAML mapping.

    Attributes:
        line: The 1-based line of the failure, or `None` when unknown.
    """

    def __init__(self, message: str, *, line: int | None = None) -> None:
        super().__init__(message)
        self.line = line


def load_mapping(path: Path) -> CommentedMap:
    """Read a YAML file whose top level must be a mapping, keeping line information.

    The result is a round-trip `CommentedMap`, so `line_of` can find any key or list item in it.

    Raises:
        YamlLoadError: If the file is unreadable, is not valid YAML, is empty or is not a mapping.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise YamlLoadError(f"cannot read file: {exc}") from exc
    try:
        data = YAML(typ="rt").load(text)
    except YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        problem = getattr(exc, "problem", None) or "syntax error"
        raise YamlLoadError(f"invalid YAML: {problem}", line=mark.line + 1 if mark else None) from exc
    if data is None:
        raise YamlLoadError("file is empty; expected a mapping with at least `schema_version`", line=1)
    if not isinstance(data, CommentedMap):
        raise YamlLoadError(f"expected a mapping at the top level, found {type(data).__name__}", line=1)
    return data


def line_of(data: CommentedMap, location: Sequence[str | int]) -> int:
    """Find the 1-based line of a key or list item, given a path such as `("conventions", "kinds")`.

    When the path leaves the data, for example a missing required key, the line of the deepest node that does exist
    is returned, so the problem points at the mapping that lacks the key.
    """
    line = 1
    node: Any = data
    for part in location:
        if isinstance(node, CommentedMap) and part in node:
            line = node.lc.key(part)[0] + 1
        elif isinstance(node, CommentedSeq) and isinstance(part, int) and 0 <= part < len(node):
            line = node.lc.item(part)[0] + 1
        else:
            break
        node = node[part]
    return line


def dump_mapping(data: CommentedMap) -> str:
    """Write a round-trip mapping back to text, keeping its comments and key order."""
    yaml = YAML(typ="rt")
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.preserve_quotes = True
    buffer = StringIO()
    yaml.dump(data, buffer)
    return buffer.getvalue()
