"""The `dpb config` command."""

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from datapatchbay.files.repo import find_repo_root
from datapatchbay.settings.effective import load_settings


def _render_value(value: Any) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(str(item) for item in value) + "]"
    return str(value)


def config(
    json_output: Annotated[bool, typer.Option("--json", help="Print the settings as JSON on stdout.")] = False,
) -> None:
    """Print the effective settings and where each one comes from."""
    settings = load_settings(find_repo_root(Path.cwd()))
    if json_output:
        typer.echo(json.dumps(settings.to_json(), indent=2))
        return
    rows = [(entry.name, _render_value(entry.value), f"({entry.origin})") for entry in settings.entries]
    name_width = max(len(name) for name, _, _ in rows)
    value_width = max(len(value) for _, value, _ in rows)
    for name, value, origin in rows:
        typer.echo(f"{name:<{name_width}}  {value:<{value_width}}  {origin}")
