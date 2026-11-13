import pytest
from plugin_fakes import FakeEntryPoint

from datapatchbay.plugins import registry
from datapatchbay.plugins.registry import PluginNotFoundError


def only(monkeypatch: pytest.MonkeyPatch, *entry_points: FakeEntryPoint) -> None:
    """Make entry point discovery find exactly these runtime entry points and nothing else."""
    monkeypatch.setattr(
        registry, "entry_points", lambda *, group: entry_points if group == "datapatchbay.runtimes" else ()
    )


@pytest.mark.parametrize(
    ("kind", "name"),
    [("orchestrator", "airflow"), ("executor", "python"), ("runtime", "worker"), ("warehouse", "postgres")],
)
def test_built_in_plugins_are_found_through_entry_points(kind, name):
    assert registry.load_plugin(kind, name) is not None
    assert name in registry.plugin_names(kind)


def test_a_registered_plugin_is_instantiated(monkeypatch: pytest.MonkeyPatch):
    only(monkeypatch, FakeEntryPoint("fake", lambda: "instance"))
    assert registry.load_plugin("runtime", "fake") == "instance"


def test_an_unknown_plugin_lists_the_available_names(monkeypatch: pytest.MonkeyPatch):
    only(monkeypatch, FakeEntryPoint("b", object), FakeEntryPoint("a", object))
    with pytest.raises(PluginNotFoundError, match=r"no runtime plugin 'nope'; available: a, b"):
        registry.load_plugin("runtime", "nope")


def test_a_name_registered_twice_is_an_error(monkeypatch: pytest.MonkeyPatch):
    only(monkeypatch, FakeEntryPoint("x", object), FakeEntryPoint("x", object))
    with pytest.raises(PluginNotFoundError, match="registered more than once"):
        registry.load_plugin("runtime", "x")


def test_a_plugin_that_cannot_be_loaded_is_named_in_the_error(monkeypatch: pytest.MonkeyPatch):
    def broken() -> None:
        raise ImportError("No module named 'snowflake'")

    only(monkeypatch, FakeEntryPoint("snow", broken))
    with pytest.raises(
        PluginNotFoundError, match=r"runtime plugin 'snow' cannot be loaded: No module named 'snowflake'"
    ):
        registry.installed_plugins()
