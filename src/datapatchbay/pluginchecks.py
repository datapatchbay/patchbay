"""The check that every orchestrator, executor, runtime and warehouse named in the settings has a plugin.

The files accept any plugin name (ADR-0009), so the check runs where the plugins are known.
"""

from pathlib import PurePosixPath

from ruamel.yaml.comments import CommentedMap

from datapatchbay.cascade import ResolvedCascade, ResolvedSetting
from datapatchbay.integrations.dbt.layout import DBT_EXECUTOR
from datapatchbay.plugins import Runtime
from datapatchbay.plugins.registry import PluginKind, load_plugin, plugin_names
from datapatchbay.problems import Problem
from datapatchbay.repo import ROOT_FILE
from datapatchbay.repomodel import DataProduct, Repo, Table
from datapatchbay.settings import EffectiveSettings
from datapatchbay.yamlio import line_of


def check_plugins(
    repo: Repo, settings: EffectiveSettings, cascade: ResolvedCascade, root_data: CommentedMap
) -> list[Problem]:
    """Report each setting that names a plugin which is not installed.

    A problem points at the line where the name is written and names the data product and, for a table, the table.
    A name set at a higher level is reported for each place it applies to, so each message names its table.
    """
    checker = _Checker(settings, cascade, root_data)
    for dataproduct in repo.dataproducts:
        checker.check(dataproduct, None, "orchestrator", "orchestrator")
        checker.check_dbt(dataproduct)
        for port in dataproduct.ports:
            for table in port.tables:
                checker.check(dataproduct, table, "executor", "executor")
                checker.check(dataproduct, table, "runtime", "runtime")
                checker.check_image(dataproduct, table)
    checker.check_warehouse()
    return checker.problems


class _Checker:
    def __init__(self, settings: EffectiveSettings, cascade: ResolvedCascade, root_data: CommentedMap) -> None:
        self._settings = settings
        self._cascade = cascade
        self._root_data = root_data
        self._names: dict[PluginKind, list[str]] = {}
        self._runtimes: dict[str, Runtime] = {}
        self.problems: list[Problem] = []

    def _installed(self, kind: PluginKind) -> list[str]:
        if kind not in self._names:
            self._names[kind] = plugin_names(kind)
        return self._names[kind]

    def check(self, dataproduct: DataProduct, table: Table | None, name: str, kind: PluginKind) -> None:
        """Check the plugin named by a setting of a data product, or of one of its tables."""
        resolved = self._cascade.for_dataproduct(dataproduct) if table is None else self._cascade.for_table(table)
        setting = resolved[name]
        if setting.value in self._installed(kind):
            return
        place = f"data product '{dataproduct.folder}'" + (f", table '{table.name}'" if table else "")
        file, line = self._where(setting)
        self.problems.append(Problem(file, line, self._message(kind, name, setting.value, place)))

    def check_image(self, dataproduct: DataProduct, table: Table) -> None:
        """Report a table whose runtime runs a container image when no level sets an image."""
        resolved = self._cascade.for_table(table)
        runtime = resolved["runtime"]
        if runtime.value not in self._installed("runtime") or not self._needs_image(str(runtime.value)):
            return
        if resolved["image"].value:
            return
        place = f"data product '{dataproduct.folder}', table '{table.name}'"
        file, line = self._where(runtime)
        message = (
            f"runtime '{runtime.value}' needs an image, but none is set ({place}); "
            "set `image` at the root, data product, port or table"
        )
        self.problems.append(Problem(file, line, message))

    def check_dbt(self, dataproduct: DataProduct) -> None:
        """Report what the dbt build task of the data product cannot do, so `dpb generate` does not fail on it.

        The tables built by dbt are built in one task, so each needs a runtime that runs dbt, they share one runtime,
        and no other table can `needs` one of them, because that task runs after the Python tables.
        """
        dbt_runtimes: dict[str, ResolvedSetting] = {}
        for port in dataproduct.ports:
            for table in port.tables:
                resolved = self._cascade.for_table(table)
                if resolved["executor"].value == DBT_EXECUTOR:
                    dbt_runtimes[table.name] = resolved["runtime"]
        first: str | None = None
        for name, runtime in dbt_runtimes.items():
            if runtime.value in self._installed("runtime") and not self._runs_dbt(str(runtime.value)):
                file, line = self._where(runtime)
                self.problems.append(
                    Problem(
                        file,
                        line,
                        f"runtime '{runtime.value}' cannot run dbt (data product '{dataproduct.folder}', table "
                        f"'{name}'); set `runtime: worker` for the tables built by dbt",
                    )
                )
            elif first is None:
                first = name
            elif runtime.value != dbt_runtimes[first].value:
                file, line = self._where(runtime)
                message = (
                    f"tables '{first}' and '{name}' of data product '{dataproduct.folder}' are built by dbt in one "
                    f"task, but their runtimes are '{dbt_runtimes[first].value}' and '{runtime.value}'"
                )
                self.problems.append(Problem(file, line, message))
        for port in dataproduct.ports:
            for table in port.tables:
                for index, need in enumerate(() if table.name in dbt_runtimes else table.needs):
                    if need in dbt_runtimes:
                        message = (
                            f"table '{table.name}' needs table '{need}', which dbt builds after the Python tables; "
                            "dbt tables cannot be needed"
                        )
                        self.problems.append(
                            Problem(table.file.path, table.file.line("build", "needs", index), message)
                        )

    def _runtime(self, name: str) -> Runtime:
        if name not in self._runtimes:
            self._runtimes[name] = load_plugin("runtime", name)
        return self._runtimes[name]

    def _runs_dbt(self, runtime: str) -> bool:
        return self._runtime(runtime).runs_dbt

    def _needs_image(self, runtime: str) -> bool:
        return self._runtime(runtime).needs_image

    def check_warehouse(self) -> None:
        value = self._settings.values.warehouse
        if value in self._installed("warehouse"):
            return
        line = line_of(self._root_data, ["warehouse"])
        self.problems.append(
            Problem(PurePosixPath(ROOT_FILE), line, self._message("warehouse", "warehouse", value, "the repo"))
        )

    def _message(self, kind: PluginKind, name: str, value: object, place: str) -> str:
        available = ", ".join(self._installed(kind)) or "none"
        return f"{name} '{value}' has no plugin ({place}); available {kind} plugins: {available}"

    def _where(self, resolved: ResolvedSetting) -> tuple[PurePosixPath, int | None]:
        """The file and line of the value; a default, or no value, points at the root file."""
        return resolved.file or PurePosixPath(ROOT_FILE), resolved.line
