"""Asking the executor plugins for their optional capabilities, so the core names no executor (ADR-0024).

An executor can add checks, produce committed files or own quality rules; each is a small protocol in
`datapatchbay.plugins` that the core checks with `isinstance`. Plugins are found by what they can do, never by name.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from datapatchbay.cascade import ResolvedCascade
from datapatchbay.errors import GenerationError
from datapatchbay.plugins import (
    ChecksDataProducts,
    ChecksPlans,
    ChecksTables,
    CommittedOutput,
    Executor,
    PlannedRepo,
    WritesCommittedFiles,
)
from datapatchbay.plugins.registry import load_plugin, plugin_names
from datapatchbay.problems import Problem
from datapatchbay.repomodel import Repo
from datapatchbay.settings import EffectiveSettings


class ExecutorPlugins:
    """The executor plugins of one run, each loaded once, so a plugin can keep what it saw between calls."""

    def __init__(self) -> None:
        self._loaded: dict[str, Executor] = {}

    def installed(self) -> list[str]:
        """The names of the installed executors, sorted."""
        return plugin_names("executor")

    def get(self, name: str) -> Executor | None:
        """The executor of that name, or `None` when none is installed, which the plugin check reports."""
        if name not in self._loaded:
            if name not in self.installed():
                return None
            self._loaded[name] = load_plugin("executor", name)
        return self._loaded[name]

    def with_capability[T](self, capability: Callable[..., T] | type[T]) -> list[T]:
        """The installed executors that have a capability, in the order of their names."""
        found: list[Any] = []
        for name in self.installed():
            executor = self.get(name)
            if isinstance(executor, capability):  # ty: ignore[invalid-argument-type]
                found.append(executor)
        return found


def check_executor_files(repo: Repo, settings: EffectiveSettings, cascade: ResolvedCascade) -> list[Problem]:
    """Stage 1: the checks that executors add for the files of each data product and each table.

    Per data product, the data product checks of every executor come first, then the table checks of the executor of
    each table in turn.
    """
    executors = ExecutorPlugins()
    for_dataproducts = executors.with_capability(ChecksDataProducts)
    problems: list[Problem] = []
    for dataproduct in repo.dataproducts:
        for checker in for_dataproducts:
            problems.extend(checker.check_dataproduct(repo, dataproduct))
        for port in dataproduct.ports:
            for table in port.tables:
                executor = executors.get(str(cascade.for_table(table)["executor"].value))
                if isinstance(executor, ChecksTables):
                    problems.extend(executor.check_table(settings, dataproduct, table))
    return problems


def check_executor_plans(planned: PlannedRepo) -> list[Problem]:
    """Stage 2: the checks that executors add on the planned repo."""
    problems: list[Problem] = []
    for checker in ExecutorPlugins().with_capability(ChecksPlans):
        problems.extend(checker.check_plans(planned))
    return problems


@dataclass(frozen=True, slots=True)
class CommittedOutputs:
    """The committed output of every executor that produces files, as one value.

    Attributes:
        outputs: One output per executor with the capability, in the order of their names.
    """

    outputs: tuple[CommittedOutput, ...]

    @property
    def orphans(self) -> tuple[PurePosixPath, ...]:
        """The generated files that nothing produces any more, relative to the repo root."""
        return tuple(sorted(path for output in self.outputs for path in output.orphans))

    def check_writable(self) -> None:
        """Raise before anything is written when an output cannot be written.

        Raises:
            GenerationError: With the message of the first output that has an error.
        """
        for output in self.outputs:
            if output.error is not None:
                raise GenerationError(output.error)

    def problems(self) -> list[Problem]:
        """The problems of every output."""
        return [problem for output in self.outputs for problem in output.problems()]

    def write(self) -> tuple[PurePosixPath, ...]:
        """Write every output; return the files written, relative to the repo root."""
        return tuple(path for output in self.outputs for path in output.write())


def committed_outputs(planned: PlannedRepo) -> CommittedOutputs:
    """Work out the committed output of the planned repo, without writing anything."""
    writers = ExecutorPlugins().with_capability(WritesCommittedFiles)
    return CommittedOutputs(tuple(writer.committed_output(planned) for writer in writers))
