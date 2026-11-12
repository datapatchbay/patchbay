"""The check that every orchestrator, executor, runtime and warehouse named in the settings has a plugin.

The files accept any plugin name (ADR-0009), so the check runs where the plugins are known.
"""

from pathlib import Path, PurePosixPath

from ruamel.yaml.comments import CommentedMap

from datapatchbay.cascade import ResolvedSetting, SettingName, resolve_setting
from datapatchbay.problems import Problem
from datapatchbay.registry import PluginKind, load_plugin, plugin_names
from datapatchbay.repo import ROOT_FILE
from datapatchbay.repomodel import DataProduct, Port, Repo, Table
from datapatchbay.settings import EffectiveSettings
from datapatchbay.yamlio import YamlLoadError, line_of, load_mapping


def check_plugins(repo: Repo, settings: EffectiveSettings) -> list[Problem]:
    """Report each setting that names a plugin which is not installed.

    A problem points at the line where the name is written and names the data product and, for a table, the table.
    A name set at a higher level is reported for each place it applies to, so each message names its table.
    """
    checker = _Checker(repo.root, settings)
    for dataproduct in repo.dataproducts:
        checker.check(dataproduct, None, None, "orchestrator", "orchestrator")
        for port in dataproduct.ports:
            for table in port.tables:
                checker.check(dataproduct, port, table, "executor", "executor")
                checker.check(dataproduct, port, table, "runtime", "runtime")
                checker.check_image(dataproduct, port, table)
    checker.check_warehouse()
    return checker.problems


class _Checker:
    def __init__(self, root: Path, settings: EffectiveSettings) -> None:
        self._root = root
        self._settings = settings
        self._names: dict[PluginKind, list[str]] = {}
        self._needs: dict[str, bool] = {}
        self.problems: list[Problem] = []
        try:
            self._root_data: CommentedMap | None = load_mapping(root / ROOT_FILE)
        except YamlLoadError:
            self._root_data = None  # reported by the loader

    def _installed(self, kind: PluginKind) -> list[str]:
        if kind not in self._names:
            self._names[kind] = plugin_names(kind)
        return self._names[kind]

    def check(
        self, dataproduct: DataProduct, port: Port | None, table: Table | None, name: SettingName, kind: PluginKind
    ) -> None:
        resolved = resolve_setting(name, self._settings, dataproduct=dataproduct, port=port, table=table)
        if resolved.value in self._installed(kind):
            return
        place = f"data product '{dataproduct.folder}'" + (f", table '{table.name}'" if table else "")
        file, line = self._where(resolved, dataproduct, port, table)
        self.problems.append(Problem(file, line, self._message(kind, name, resolved.value, place)))

    def check_image(self, dataproduct: DataProduct, port: Port, table: Table) -> None:
        """Report a table whose runtime runs a container image when no level sets an image."""
        runtime = resolve_setting("runtime", self._settings, dataproduct=dataproduct, port=port, table=table)
        if runtime.value not in self._installed("runtime") or not self._needs_image(str(runtime.value)):
            return
        if resolve_setting("image", self._settings, dataproduct=dataproduct, port=port, table=table).value:
            return
        place = f"data product '{dataproduct.folder}', table '{table.name}'"
        file, line = self._where(runtime, dataproduct, port, table)
        message = (
            f"runtime '{runtime.value}' needs an image, but none is set ({place}); "
            "set `image` at the root, data product, port or table"
        )
        self.problems.append(Problem(file, line, message))

    def _needs_image(self, runtime: str) -> bool:
        if runtime not in self._needs:
            self._needs[runtime] = bool(getattr(load_plugin("runtime", runtime), "needs_image", False))
        return self._needs[runtime]

    def check_warehouse(self) -> None:
        value = self._settings.values.warehouse
        if value in self._installed("warehouse"):
            return
        line = line_of(self._root_data, ["warehouse"]) if self._root_data is not None else None
        self.problems.append(
            Problem(PurePosixPath(ROOT_FILE), line, self._message("warehouse", "warehouse", value, "the repo"))
        )

    def _message(self, kind: PluginKind, name: str, value: object, place: str) -> str:
        available = ", ".join(self._installed(kind)) or "none"
        return f"{name} '{value}' has no plugin ({place}); available {kind} plugins: {available}"

    def _where(
        self, resolved: ResolvedSetting, dataproduct: DataProduct, port: Port | None, table: Table | None
    ) -> tuple[PurePosixPath, int | None]:
        key = resolved.name
        if resolved.level == "table" and table is not None:
            return table.file.path, table.file.line("build", key)
        if resolved.level == "port" and port is not None:
            return port.file.path, port.file.line(key)
        if resolved.level == "dataproduct":
            return dataproduct.file.path, dataproduct.file.line(key)
        line = line_of(self._root_data, [key]) if self._root_data is not None and resolved.level == "root" else None
        return PurePosixPath(ROOT_FILE), line
