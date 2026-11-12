"""The `dpb upgrade` command."""

import difflib
from pathlib import Path
from typing import Annotated

import typer

from datapatchbay import upgrade as upgrade_module
from datapatchbay.repo import find_repo_root


def upgrade(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would change and write nothing.")] = False,
) -> None:
    """Rewrite every file to the current schema version, keeping comments and key order."""
    result = upgrade_module.upgrade_repo(find_repo_root(Path.cwd()), dry_run=dry_run)
    if result.problems:
        for problem in result.problems:
            typer.echo(problem.render(), err=True)
        typer.echo("nothing was changed", err=True)
        raise typer.Exit(code=1)
    if not result.changes:
        typer.echo("nothing to do: every file is at the current schema version")
        return
    verb = "would upgrade" if dry_run else "upgraded"
    for change in result.changes:
        typer.echo(f"{verb} {change.file} ({change.from_version} -> {change.to_version})")
        if dry_run:
            diff = difflib.unified_diff(
                change.before.splitlines(keepends=True),
                change.after.splitlines(keepends=True),
                fromfile=f"a/{change.file}",
                tofile=f"b/{change.file}",
            )
            typer.echo("".join(diff), nl=False)
