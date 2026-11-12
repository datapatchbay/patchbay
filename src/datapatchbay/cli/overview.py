"""The `dpb list` and `dpb describe` commands."""

import json
from pathlib import Path
from typing import Annotated

import typer

from datapatchbay.describe import (
    describe_dataproduct,
    find_dataproduct,
    list_dataproducts,
    render_description,
    render_list,
)
from datapatchbay.loading import load_repo
from datapatchbay.repo import find_repo_root
from datapatchbay.repomodel import Repo
from datapatchbay.settings import EffectiveSettings, load_settings


def _load() -> tuple[Repo, EffectiveSettings]:
    """Load what is readable; files with problems are left out and counted on stderr."""
    root = find_repo_root(Path.cwd())
    settings = load_settings(root)
    repo, problems = load_repo(root)
    if problems:
        typer.echo(f"warning: {len(problems)} problem(s) found; run `dpb validate` for details", err=True)
    return repo, settings


def list_command(
    json_output: Annotated[bool, typer.Option("--json", help="Print the data products as JSON on stdout.")] = False,
) -> None:
    """List every data product with its kind, domain, owner and technical owner."""
    repo, _ = _load()
    entries = list_dataproducts(repo)
    typer.echo(json.dumps(entries, indent=2) if json_output else render_list(entries))


def describe(
    dataproduct: Annotated[str, typer.Argument(help="Folder name or name of the data product.")],
    json_output: Annotated[bool, typer.Option("--json", help="Print the description as JSON on stdout.")] = False,
) -> None:
    """Describe one data product: ports, tables, columns, quality rules, freshness, readers and resolved settings."""
    repo, settings = _load()
    description = describe_dataproduct(repo, settings, find_dataproduct(repo, dataproduct))
    typer.echo(json.dumps(description, indent=2) if json_output else render_description(description))
