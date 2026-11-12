"""Rewriting files to the current schema version, one migration step at a time (ADR-0011)."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ruamel.yaml.comments import CommentedMap

from datapatchbay.files.repo import ROOT_FILE, find_dataproduct_files, find_port_and_table_files
from datapatchbay.files.yamlio import YamlLoadError, dump_mapping, line_of, load_mapping
from datapatchbay.models import SCHEMA_VERSION
from datapatchbay.problems import Problem


@dataclass(frozen=True, slots=True)
class Migration:
    """One step from schema version n to n+1, registered under n.

    Attributes:
        apply: Edits the file's mapping in place. It does not touch `schema_version`; the runner bumps it.
    """

    apply: Callable[[CommentedMap], None]


MIGRATIONS: Mapping[int, Migration] = {}
"""The migrations that ship, keyed by the version they start from. Empty: version 1 is the only version."""


@dataclass(frozen=True, slots=True)
class FileChange:
    """One file that was, or with a dry run would be, rewritten."""

    file: PurePosixPath
    from_version: int
    to_version: int
    before: str
    after: str


@dataclass(frozen=True, slots=True)
class UpgradeResult:
    """The outcome of an upgrade: the files changed, or the problems that stopped it before anything was written."""

    changes: list[FileChange]
    problems: list[Problem]


def rename_key(data: CommentedMap, old: str, new: str) -> None:
    """Rename a key in place, keeping its position, its value and the comment on its line."""
    position = list(data).index(old)
    comment = data.ca.items.pop(old, None)
    value = data.pop(old)
    data.insert(position, new, value)
    if comment is not None:
        data.ca.items[new] = comment
        trailing = comment[2]
        if trailing is not None and trailing.column is not None:
            # ruamel writes the comment at a fixed column, so follow the key's change in length.
            trailing.column += len(new) - len(old)


def upgrade_repo(
    root: Path,
    *,
    dry_run: bool = False,
    migrations: Mapping[int, Migration] | None = None,
    current_version: int | None = None,
) -> UpgradeResult:
    """Bring every file in the repo to the current schema version.

    Nothing is written when any file is refused, so a repo is never left half upgraded. With `dry_run`, nothing is
    written at all.

    Keyword Args:
        dry_run: Compute the changes without writing them.
        migrations: The migration steps, keyed by starting version. Defaults to the shipped `MIGRATIONS`.
        current_version: The version to upgrade to. Defaults to `SCHEMA_VERSION`.

    Returns:
        The changes made (or planned) and the problems that refused the upgrade.
    """
    steps = MIGRATIONS if migrations is None else migrations
    target = SCHEMA_VERSION if current_version is None else current_version
    files = [root / ROOT_FILE, *find_dataproduct_files(root), *find_port_and_table_files(root)]

    changes: list[FileChange] = []
    problems: list[Problem] = []
    for path in files:
        relative = PurePosixPath(path.relative_to(root).as_posix())
        try:
            change = _upgrade_file(path, relative, steps, target)
        except _Refused as refusal:
            problems.append(Problem(relative, refusal.line, str(refusal)))
            continue
        if change is not None:
            changes.append(change)

    if problems:
        return UpgradeResult([], problems)
    if not dry_run:
        for change in changes:
            (root / change.file).write_text(change.after, encoding="utf-8")
    return UpgradeResult(changes, [])


class _Refused(Exception):
    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.line = line


def _upgrade_file(
    path: Path, relative: PurePosixPath, steps: Mapping[int, Migration], target: int
) -> FileChange | None:
    try:
        data = load_mapping(path)
    except YamlLoadError as exc:
        raise _Refused(str(exc), exc.line) from exc

    version = data.get("schema_version")
    line = line_of(data, ["schema_version"])
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise _Refused("missing or invalid schema_version; run `dpb validate` and fix it first", line)
    if version > target:
        raise _Refused(
            f"schema_version {version} is newer than this datapatchbay understands "
            f"(newest known: {target}); upgrade datapatchbay",
            line,
        )
    if version == target:
        return None

    before = path.read_text(encoding="utf-8")
    for current in range(version, target):
        step = steps.get(current)
        if step is None:
            raise _Refused(f"no migration from schema_version {current} to {current + 1}", line)
        step.apply(data)
        data["schema_version"] = current + 1
    return FileChange(relative, version, target, before, dump_mapping(data))
