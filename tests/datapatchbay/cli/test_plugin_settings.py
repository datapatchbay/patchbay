"""A plugin declares a settings section and naming templates (ADR-0025); the core handles them without naming it."""

import json
from pathlib import Path

import pytest
from plugin_fakes import AcmeWarehouse, install_distribution
from typer.testing import CliRunner

from datapatchbay.cli import app
from datapatchbay.commands.schemas import json_schema
from datapatchbay.pipeline.generate import generate_repo
from datapatchbay.plugins import DeclaredSettings
from datapatchbay.settings.effective import load_settings
from datapatchbay.settings.pluginsettings import PluginSettingsError, declarations_of, root_model

ACME = "warehouse: acme\nacme:\n  endpoint: https://prod.example\nconventions:\n  names:\n    acme_schema: 'x_{name}'\n"


@pytest.fixture
def acme_repo(repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A repo whose warehouse is a third-party plugin installed through entry-point metadata."""
    install_distribution(
        monkeypatch, tmp_path_factory.mktemp("site"), "warehouse", "acme", "plugin_fakes:AcmeWarehouse"
    )
    (repo / "datapatchbay.yaml").write_text("schema_version: 1\n" + ACME)
    return repo


def test_config_shows_the_section_and_template_of_a_third_party_plugin(runner: CliRunner, acme_repo: Path):
    data = json.loads(runner.invoke(app, ["config", "--json"]).stdout)
    assert data["acme.endpoint"] == {"value": "https://prod.example", "origin": "datapatchbay.yaml"}
    assert data["acme.retries"] == {"value": 3, "origin": "defaults of plugin acme"}
    assert data["conventions.names.acme_schema"] == {"value": "x_{name}", "origin": "datapatchbay.yaml"}


def test_config_text_names_the_plugin_that_owns_a_default(runner: CliRunner, acme_repo: Path):
    (acme_repo / "datapatchbay.yaml").write_text("schema_version: 1\nwarehouse: acme\n")
    lines = runner.invoke(app, ["config"]).stdout.splitlines()
    [retries] = [line.split() for line in lines if line.startswith("acme.retries")]
    assert retries == ["acme.retries", "3", "(defaults", "of", "plugin", "acme)"]


def test_the_resolved_section_is_on_the_settings(acme_repo: Path):
    settings = load_settings(acme_repo)
    assert settings.plugins["acme"].model_dump() == {"endpoint": "https://prod.example", "retries": 3}
    assert settings.values.conventions.plugin_names["acme_schema"] == "x_{name}"


def test_the_plan_hands_the_resolved_section_to_the_plugin(jaffle_repo: Path, acme_repo: Path):
    (jaffle_repo / "datapatchbay.yaml").write_text("schema_version: 1\n" + ACME)
    result = generate_repo(jaffle_repo)
    assert result.report.ok, result.report.problems
    assert "-- https://prod.example" in (jaffle_repo / "generated/sa_jaffle_orders.py").read_text()


def test_validate_accepts_the_section(runner: CliRunner, acme_repo: Path):
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.output


def test_validate_rejects_a_bad_value_in_the_section_with_its_line(runner: CliRunner, acme_repo: Path):
    (acme_repo / "datapatchbay.yaml").write_text("schema_version: 1\nacme:\n  retries: -1\n")
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1
    assert "datapatchbay.yaml:3: acme.retries:" in result.output


def test_validate_rejects_an_unknown_key_in_the_section(runner: CliRunner, acme_repo: Path):
    (acme_repo / "datapatchbay.yaml").write_text("schema_version: 1\nacme:\n  retry: 1\n")
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1
    assert "datapatchbay.yaml:3: unknown key 'acme.retry'" in result.output


def test_validate_checks_the_placeholders_of_the_plugin_template(runner: CliRunner, acme_repo: Path):
    (acme_repo / "datapatchbay.yaml").write_text(
        "schema_version: 1\nconventions:\n  names:\n    acme_schema: '{region}_{bogus}'\n"
    )
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1
    assert "datapatchbay.yaml:4: conventions.names.acme_schema: naming template" in result.output
    assert "{bogus}" in result.output
    assert "{region}" in result.output  # the extra placeholder the plugin declares is available


def test_a_section_that_no_installed_plugin_declares_is_an_unknown_key(runner: CliRunner, repo: Path):
    (repo / "datapatchbay.yaml").write_text("schema_version: 1\nacme:\n  retries: 1\n")
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1
    assert "datapatchbay.yaml:2: unknown key 'acme'; no installed plugin declares a settings section 'acme'" in (
        result.output
    )


def test_the_root_schema_includes_the_section_and_template_of_installed_plugins(acme_repo: Path):
    schema = json_schema("root")
    assert schema["properties"]["acme"]["description"] == "Settings of the Acme warehouse."
    section = schema["$defs"]["AcmeSection"]["properties"]
    assert section["retries"]["description"] == "How many times a statement is retried."
    names = schema["$defs"]["NamesConvention"]["properties"]
    assert names["acme_schema"]["description"] == "Naming template of an Acme schema."


def test_the_root_schema_has_no_section_when_the_plugin_is_not_installed(repo: Path):
    schema = json_schema("root")
    assert "acme" not in schema["properties"]
    assert "acme_schema" not in schema["$defs"]["NamesConvention"]["properties"]


def test_the_plugin_name_must_not_be_a_core_setting(runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch):
    install_distribution(monkeypatch, repo / "site", "warehouse", "runtime", "plugin_fakes:RuntimeNamedWarehouse")
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 2
    assert "the warehouse plugin 'runtime' declares a settings section, but 'runtime' is a setting" in result.output


def test_two_plugins_cannot_declare_the_same_section_or_template():
    acme = ("warehouse", "acme", AcmeWarehouse())
    with pytest.raises(PluginSettingsError, match="declares a settings section that the warehouse plugin 'acme'"):
        declarations_of([acme, ("executor", "acme", AcmeWarehouse())])
    other = ("executor", "other", AcmeWarehouse())
    with pytest.raises(PluginSettingsError, match="naming template 'acme_schema', which another plugin declares"):
        declarations_of([acme, other])


def test_a_plugin_cannot_declare_a_core_naming_template():
    class Bad:
        declared_settings = DeclaredSettings(
            naming_templates={"role": AcmeWarehouse.declared_settings.naming_templates["acme_schema"]}
        )

    with pytest.raises(PluginSettingsError, match="'role', which a core naming template declares"):
        declarations_of([("warehouse", "bad", Bad())])


def test_defaults_that_the_section_rejects_are_refused():
    class Bad:
        declared_settings = DeclaredSettings(section=AcmeWarehouse.declared_settings.section, defaults={"retries": -1})

    with pytest.raises(PluginSettingsError, match="defaults of the settings section 'bad'"):
        declarations_of([("warehouse", "bad", Bad())])


def test_a_plugin_that_declares_nothing_changes_nothing():
    assert root_model(declarations_of([("warehouse", "plain", object())])).__name__ == "RootFile"
