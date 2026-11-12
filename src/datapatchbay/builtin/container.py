"""What the container runtimes share: how the entrypoint and its params reach the code in the container (ADR-0016).

The container runs `python -c LOADER FILE FUNCTION PARAMS`. The loader is a few lines of standard library Python, so
the image needs a `python` and the build code and nothing of datapatchbay (ADR-0001). `FILE` is relative to the
container's working directory, which the image sets to the data product folder.
"""

import json
import keyword
from collections.abc import Mapping
from typing import Any

from datapatchbay.literals import python_literal
from datapatchbay.plugins import BuildTask, PythonCall, UnsupportedCombinationError

ENTRYPOINT_LOADER = """\
import importlib.util, json, sys
file, function, params = sys.argv[1:4]
spec = importlib.util.spec_from_file_location("datapatchbay_build", file)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
getattr(module, function)(**json.loads(params))"""
"""The program that loads the entrypoint file and calls the function with the params. It has no braces that Jinja
would read as a template."""

_INDENT = "    "


def python_call_of(task: BuildTask, runtime: str) -> PythonCall:
    """Return the task's Python call.

    Raises:
        UnsupportedCombinationError: If the executor asks for something else, such as a `dbt build`, which only the
            worker runtime runs.
    """
    if not isinstance(task.call, PythonCall):
        raise UnsupportedCombinationError(
            f"the {runtime} runtime cannot run dbt: set `runtime: worker` for the tables built by dbt"
        )
    return task.call


def image_of(task: BuildTask, runtime: str) -> str:
    """Return the table's image.

    Raises:
        UnsupportedCombinationError: If the table has no image.
    """
    image = task.table.image
    if not image:
        raise UnsupportedCombinationError(
            f"table '{task.table.name}' has no image, which the {runtime} runtime needs; set `image`"
        )
    return image


def loader_arguments(task: BuildTask, runtime: str) -> list[str]:
    """Return the arguments of `python`: the loader, then the file, the function and the params as JSON.

    Raises:
        UnsupportedCombinationError: If the task is not a Python call.
        ValueError: If a param is not a plain YAML value.
    """
    call = python_call_of(task, runtime)
    python_literal(call.params)  # refuses what YAML reads as a date or other non-plain value
    params = json.dumps(dict(call.params), separators=(",", ":"), ensure_ascii=False)
    return ["-c", ENTRYPOINT_LOADER, call.file.as_posix(), call.function, params]


def operator_call(
    variable: str, operator: str, set_by_dpb: Mapping[str, Any], container: Mapping[str, Any]
) -> tuple[str, ...]:
    """Write `variable = operator(...)` with the arguments dpb sets, then the `container` setting as written.

    The `container` arguments are sorted by name, so the file does not depend on their order in YAML.

    Raises:
        UnsupportedCombinationError: If `container` names an argument that dpb sets, or a name that is not an
            argument name.
        ValueError: If a value is not a plain YAML value.
    """
    for key in container:
        if not isinstance(key, str) or not key.isidentifier() or keyword.iskeyword(key):
            raise UnsupportedCombinationError(f"container setting '{key}' is not an argument name of {operator}")
        if key in set_by_dpb:
            raise UnsupportedCombinationError(
                f"container setting '{key}' would replace what dpb sets on {operator}; dpb sets {', '.join(set_by_dpb)}"
            )
    arguments = {**set_by_dpb, **dict(sorted(container.items()))}
    return (
        f"{variable} = {operator}(",
        *(f"{_INDENT}{key}={python_literal(value)}," for key, value in arguments.items()),
        ")",
    )
