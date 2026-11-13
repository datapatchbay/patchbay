"""Finding plugins through Python entry points (ADR-0009). The built-in plugins are registered the same way."""

from importlib.metadata import entry_points
from typing import Any, Literal

from datapatchbay.errors import DatapatchbayError

type PluginKind = Literal["orchestrator", "executor", "runtime", "warehouse"]

PLUGIN_KINDS: tuple[PluginKind, ...] = ("orchestrator", "executor", "runtime", "warehouse")

GROUPS: dict[PluginKind, str] = {
    "orchestrator": "datapatchbay.orchestrators",
    "executor": "datapatchbay.executors",
    "runtime": "datapatchbay.runtimes",
    "warehouse": "datapatchbay.warehouses",
}
"""The entry point group of each extension point. An entry point refers to a class, or a function without
arguments, that returns the plugin."""


class PluginNotFoundError(DatapatchbayError):
    """Raised when no plugin of a name is registered, or when the name is registered more than once."""


def plugin_names(kind: PluginKind) -> list[str]:
    """Return the names registered for an extension point, sorted and without duplicates."""
    return sorted({entry.name for entry in entry_points(group=GROUPS[kind])})


def load_plugin(kind: PluginKind, name: str) -> Any:
    """Create the plugin registered under a name.

    Args:
        kind: The extension point.
        name: The plugin's name, as written in the settings.

    Returns:
        A new plugin object. The caller types it as the matching `Protocol`.

    Raises:
        PluginNotFoundError: If no plugin has that name, or two entry points have it.
    """
    matches = [entry for entry in entry_points(group=GROUPS[kind]) if entry.name == name]
    if not matches:
        available = ", ".join(plugin_names(kind)) or "none"
        raise PluginNotFoundError(f"no {kind} plugin '{name}'; available: {available}")
    if len(matches) > 1:
        raise PluginNotFoundError(f"{kind} plugin '{name}' is registered more than once")
    return matches[0].load()()


def installed_plugins() -> list[tuple[PluginKind, str, Any]]:
    """Create every installed plugin, for the core to ask what each one declares (ADR-0025).

    Returns:
        One `(kind, name, plugin)` per registered name and extension point, in a fixed order: the order of
        `PLUGIN_KINDS`, then by name. A name that two entry points register is created from the first.

    Raises:
        PluginNotFoundError: If an installed plugin cannot be imported or created; the message names it.
    """
    found: list[tuple[PluginKind, str, Any]] = []
    for kind in PLUGIN_KINDS:
        entries = {entry.name: entry for entry in reversed(list(entry_points(group=GROUPS[kind])))}
        for name in sorted(entries):
            try:
                plugin = entries[name].load()()
            except Exception as exc:  # a broken third-party plugin must name itself, not end in a traceback
                raise PluginNotFoundError(f"{kind} plugin '{name}' cannot be loaded: {exc}") from exc
            found.append((kind, name, plugin))
    return found
