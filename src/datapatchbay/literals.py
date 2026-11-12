"""Writing YAML values as Python source, for generated files that must stand alone (ADR-0001)."""

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any


def python_literal(value: Any) -> str:
    """Write a plain YAML value as a Python literal, the same way every time. Strings use double quotes.

    Mappings keep the order of the file. Types that the YAML reader adds, such as ruamel.yaml's scalar subclasses,
    are written as their plain type.

    Raises:
        ValueError: If the value is not a string, number, boolean, null, list or mapping with string keys, such as
            an unquoted date, or if a number is not finite.
    """
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return repr(int(value))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{value} cannot be written as a Python literal")
        return repr(float(value))
    if isinstance(value, str):
        return json.dumps(str(value), ensure_ascii=False)
    if isinstance(value, Mapping):
        items = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"key {key!r} is not a string")
            items.append(f"{python_literal(key)}: {python_literal(item)}")
        return "{" + ", ".join(items) + "}"
    if isinstance(value, Sequence):
        return "[" + ", ".join(python_literal(item) for item in value) + "]"
    raise ValueError(f"a {type(value).__name__} ({value!r}) is not a plain value; quote it to write it as text")
