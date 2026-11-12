"""The minimal warehouse of docs/plugins.md runs, and imports nothing but `datapatchbay.plugins`."""

import ast
import re
from pathlib import Path
from typing import Any

import datapatchbay

PAGE = Path(datapatchbay.__file__).parents[2] / "docs" / "plugins.md"


def example() -> str:
    match = re.search(r"```python\n(.*?)```", PAGE.read_text(), re.S)
    assert match
    return match.group(1)


def test_the_example_imports_only_the_public_plugin_modules():
    imported = {node.module for node in ast.walk(ast.parse(example())) if isinstance(node, ast.ImportFrom)}
    assert imported <= {"collections.abc", "datapatchbay.plugins", "datapatchbay.plugins.sql"}


def test_the_example_warehouse_defines_the_warehouse_interface():
    namespace: dict[str, Any] = {}
    exec(example(), namespace)
    warehouse = namespace["MyWarehouse"]()
    assert callable(warehouse.apply_tasks)
    assert callable(warehouse.audit_tasks)
    assert namespace["DIALECT"].identifier("a`b") == "`a``b`"
