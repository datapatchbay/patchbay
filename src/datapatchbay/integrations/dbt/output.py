"""The committed dbt output of a repo as one value: what `dpb generate` writes and `dpb validate` compares (ADR-0013).

The dbt properties, sources and singular tests (ADR-0018, ADR-0019) and the `model-paths` and `test-paths` of the
root `dbt_project.yml` are generated and committed next to the models. `build_dbt_output` works out all of it from
the planned repo, once, without writing anything. The value then does both jobs: `DbtOutput.write` writes it (files,
then orphan deletions, then `dbt_project.yml` last) and `DbtOutput.problems` diffs it against the files on disk, so
the two cannot drift. Nothing here imports or runs dbt (ADR-0004).
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from operator import attrgetter
from pathlib import Path, PurePosixPath

from ruamel.yaml.comments import CommentedSeq

from datapatchbay.filewrite import remove_file, write_file
from datapatchbay.genheader import generated_from
from datapatchbay.integrations.dbt.layout import DBT_EXECUTOR, MODELS_FOLDER, TESTS_FOLDER
from datapatchbay.integrations.dbt.project import DBT_PROJECT_FILE, DbtProjectError, synced_dbt_project
from datapatchbay.integrations.dbt.properties import GROUP_FILE, generate_dbt_properties
from datapatchbay.integrations.dbt.sources import generate_dbt_sources
from datapatchbay.integrations.dbt.tests import generate_dbt_tests
from datapatchbay.planning import PlannedRepo
from datapatchbay.plugins import DataProductPlan
from datapatchbay.problems import Problem
from datapatchbay.repomodel import Repo
from datapatchbay.yamlio import YamlLoadError, load_mapping

__all__ = ["DbtFile", "DbtFileKind", "DbtOutput", "DbtProjectChange", "build_dbt_output", "model_paths"]

_REFRESH = "run `dpb generate` to refresh it"


class DbtFileKind(StrEnum):
    """What a generated dbt file is."""

    PROPERTIES = "properties"
    SOURCES = "sources"
    TEST = "test"

    @property
    def label(self) -> str:
        """The name of the kind in a problem message: sources are properties files to dbt."""
        return "dbt test file" if self is DbtFileKind.TEST else "dbt properties file"


@dataclass(frozen=True, slots=True)
class DbtFile:
    """A generated dbt file.

    Attributes:
        path: Relative to the repo root.
        content: The text `dpb generate` writes.
        kind: Which generator made it.
    """

    path: PurePosixPath
    content: str
    kind: DbtFileKind


@dataclass(frozen=True, slots=True)
class DbtProjectChange:
    """The new text of the root `dbt_project.yml`, when it is not in step.

    Attributes:
        path: The absolute path of the file.
        content: The new text.
    """

    path: Path
    content: str


@dataclass(frozen=True, slots=True)
class DbtOutput:
    """The committed dbt output of a planned repo.

    Attributes:
        root: The repo root.
        files: Every generated file, sorted by path.
        orphans: Files with the generated header in a `models/` or `tests/` folder that no table produces any more,
            relative to the repo root, sorted.
        model_paths: The `models/` folder of every data product with a table built by dbt, relative to the root.
        test_paths: The `tests/` folders of those data products.
        project: The new `dbt_project.yml`, or `None` when it is in step.
        project_error: Why `dbt_project.yml` cannot be synced (tables are built by dbt and it is missing or not a YAML
            mapping), or `None`.
    """

    root: Path
    files: tuple[DbtFile, ...]
    orphans: tuple[PurePosixPath, ...]
    model_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    project: DbtProjectChange | None
    project_error: str | None

    def problems(self) -> list[Problem]:
        """Diff the output with the files on disk, and look for hand-written duplicates of a model.

        Returns:
            The problems found, empty when dbt builds no table and nothing is left over, or the files are in step.
        """
        problems: list[Problem] = []
        for file in self.files:
            problems.extend(self._compare(file))
        project = PurePosixPath(DBT_PROJECT_FILE)
        if self.project is not None:
            problems.append(
                Problem(
                    project,
                    None,
                    f"`model-paths` or `test-paths` does not list the `{MODELS_FOLDER}/` and `{TESTS_FOLDER}/` folders "
                    f"of the data products built by dbt; {_REFRESH}",
                )
            )
        if self.project_error is not None:
            problems.append(Problem(project, None, self.project_error))
        problems.extend(
            Problem(path, None, "dbt file is no longer generated from the table files; delete it")
            for path in self.orphans
        )
        problems.extend(self._duplicates())
        return problems

    def write(self, write: Callable[[Path, str], None] = write_file) -> tuple[PurePosixPath, ...]:
        """Write the files, then delete the orphans, then write `dbt_project.yml` last.

        The order means a failed write leaves the committed `dbt_project.yml` as it was.

        Args:
            write: Writes one file; defaults to a whole-or-nothing write. Raises `GenerationError` on failure.

        Returns:
            The files written, relative to the repo root: the generated files, then `dbt_project.yml` if it changed.

        Raises:
            GenerationError: If a file cannot be written or deleted.
        """
        committed = []
        for file in self.files:
            write(self.root / file.path, file.content)
            committed.append(file.path)
        for path in self.orphans:
            remove_file(self.root / path)
        if self.project is not None:
            write(self.project.path, self.project.content)
            committed.append(PurePosixPath(self.project.path.relative_to(self.root).as_posix()))
        return tuple(committed)

    def _compare(self, file: DbtFile) -> list[Problem]:
        path = self.root / file.path
        if not path.is_file():
            return [Problem(file.path, None, f"{file.kind.label} is missing; {_REFRESH}")]
        if path.read_bytes() != file.content.encode("utf-8"):
            return [Problem(file.path, None, f"{file.kind.label} does not match its table file; {_REFRESH}")]
        return []

    def _duplicates(self) -> list[Problem]:
        built = {
            file.path.stem: file.path
            for file in self.files
            if file.kind is DbtFileKind.PROPERTIES and file.path.name != GROUP_FILE
        }
        generated_paths = {file.path for file in self.files}
        problems: list[Problem] = []
        for folder in self.model_paths:
            directory = self.root / folder
            if not directory.is_dir():
                continue
            for path in sorted([*directory.rglob("*.yml"), *directory.rglob("*.yaml")]):
                relative = PurePosixPath(path.relative_to(self.root).as_posix())
                if relative not in generated_paths:
                    problems.extend(_duplicates_in(path, relative, built))
        return problems


def model_paths(plans: Sequence[DataProductPlan]) -> tuple[str, ...]:
    """List the `models/` folder of every data product that has a table built by dbt.

    Returns:
        The folders relative to the repo root, in posix form, sorted. Empty when dbt builds no table.
    """
    return _folders(plans, MODELS_FOLDER)


def build_dbt_output(planned: PlannedRepo) -> DbtOutput:
    """Work out the committed dbt output of a repo that passed the gate, without writing anything.

    The files come from the plans; the orphans and the new `dbt_project.yml` come from comparing with what is on disk.

    Args:
        planned: The repo that passed the gate, with its plans.
    """
    repo, settings, plans = planned.repo, planned.settings, planned.plans
    kinded = [
        (DbtFileKind.PROPERTIES, generate_dbt_properties(plans, settings)),
        (DbtFileKind.SOURCES, generate_dbt_sources(plans)),
        (DbtFileKind.TEST, generate_dbt_tests(plans, settings)),
    ]
    files = tuple(
        sorted(
            (DbtFile(file.path, file.content, kind) for kind, made in kinded for file in made), key=attrgetter("path")
        )
    )
    models, tests = _folders(plans, MODELS_FOLDER), _folders(plans, TESTS_FOLDER)
    project: DbtProjectChange | None = None
    project_error: str | None = None
    try:
        synced = synced_dbt_project(repo.root, models, tests)
        project = None if synced is None else DbtProjectChange(*synced)
    except DbtProjectError as exc:
        project_error = str(exc)
    return DbtOutput(repo.root, files, tuple(_orphans(repo, files)), models, tests, project, project_error)


def _folders(plans: Sequence[DataProductPlan], name: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                (plan.source.file.path.parent / name).as_posix()
                for plan in plans
                if any(table.executor == DBT_EXECUTOR for table in plan.tables)
            }
        )
    )


def _orphans(repo: Repo, files: Sequence[DbtFile]) -> list[PurePosixPath]:
    """Find the files that carry the generated header in a `models/` or `tests/` folder but are not in `files`.

    These are left behind when a table is no longer built by dbt, a table is removed or a table rule is removed. Every
    data product is scanned, whether or not its folders are still in `model-paths` or `test-paths`, because a
    product that dbt no longer builds drops out of them while its generated files stay on disk. A file without the
    header is hand-written and never an orphan.
    """
    wanted = {file.path for file in files}
    orphans = []
    for dataproduct in repo.dataproducts:
        for folder, patterns in ((MODELS_FOLDER, ("*.yml", "*.yaml")), (TESTS_FOLDER, ("*.sql",))):
            directory = dataproduct.directory / folder
            if not directory.is_dir():
                continue
            for path in (found for pattern in patterns for found in directory.rglob(pattern)):
                relative = PurePosixPath(path.relative_to(repo.root).as_posix())
                if relative not in wanted and generated_from(path) is not None:
                    orphans.append(relative)
    return sorted(orphans)


def _duplicates_in(path: Path, relative: PurePosixPath, built: Mapping[str, PurePosixPath]) -> list[Problem]:
    try:
        data = load_mapping(path)
    except YamlLoadError:
        return []  # not a dbt properties file, or not YAML; dbt reports its own files
    entries = data.get("models")
    if not isinstance(entries, CommentedSeq):
        return []
    problems = []
    for index, entry in enumerate(entries):
        name = entry.get("name") if hasattr(entry, "get") else None
        if isinstance(name, str) and name in built:
            problems.append(
                Problem(
                    relative,
                    entries.lc.item(index)[0] + 1,
                    f"model '{name}' is already declared in {built[name]}, which `dpb generate` writes from its "
                    "table file; remove this entry",
                )
            )
    return problems
