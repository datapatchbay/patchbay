"""The minimal warehouse of docs/plugins.md runs, and imports nothing but `datapatchbay.plugins`."""

import ast
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from container_helpers import table_of

import datapatchbay
from datapatchbay.plugins import CommandCall
from datapatchbay.settings.pluginsettings import declarations_of, root_model

PAGE = Path(datapatchbay.__file__).parents[2] / "docs" / "plugins.md"


def example(name: str = "MyWarehouse") -> str:
    """Return the Python block of the page that defines the class `name`."""
    blocks = re.findall(r"```python\n(.*?)```", PAGE.read_text(), re.S)
    [block] = [block for block in blocks if re.search(rf"^class {name}\b", block, re.M)]
    return block


@pytest.mark.parametrize("name", ["MyWarehouse", "MyToolExecutor", "MyConfigurableWarehouse"])
def test_the_example_imports_only_the_public_plugin_modules(name: str):
    imported = {node.module for node in ast.walk(ast.parse(example(name))) if isinstance(node, ast.ImportFrom)}
    assert imported <= {"collections.abc", "pydantic", "datapatchbay.plugins", "datapatchbay.plugins.sql"}


def test_the_example_warehouse_defines_the_warehouse_interface():
    namespace: dict[str, Any] = {}
    exec(example(), namespace)
    warehouse = namespace["MyWarehouse"]()
    assert callable(warehouse.apply_tasks)
    assert callable(warehouse.audit_tasks)
    assert namespace["DIALECT"].identifier("a`b") == "`a``b`"


def test_the_example_executor_returns_a_command_call(jaffle_repo: Path):
    namespace: dict[str, Any] = {}
    exec(example("MyToolExecutor"), namespace)
    table = table_of(jaffle_repo)
    call = namespace["MyToolExecutor"]().call(table)
    assert call == CommandCall(
        argv=("mytool", "run", "--config", "~/.mytool"), cwd="../..", env={"MYTOOL_TABLE": table.name}, home_args=(3,)
    )


def test_the_example_that_declares_settings_is_read_by_the_core(jaffle_repo: Path):
    namespace: dict[str, Any] = {}
    exec(example("MyConfigurableWarehouse"), namespace)
    plugin = namespace["MyConfigurableWarehouse"]()
    declarations = declarations_of([("warehouse", "mywarehouse", plugin)])
    [section] = declarations.sections
    assert (section.plugin, dict(section.defaults)) == ("mywarehouse", {"retries": 3})
    [template] = declarations.templates
    assert (template.name, template.template.default) == ("mywarehouse_schema", "mw_{name}")
    assert "mywarehouse" in root_model(declarations).model_fields

    values = namespace["MyWarehouseSection"].model_validate({"retries": 5})
    plan = SimpleNamespace(plugin_settings={"mywarehouse": values})
    [task] = plugin.apply_tasks(plan)
    assert task.sql == "-- retry 5 times"
