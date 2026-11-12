"""The `dpb generate` command."""

import json
from pathlib import Path
from typing import Annotated

import typer

from datapatchbay.generate import generate_repo
from datapatchbay.repo import find_repo_root


def generate(
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Folder to write to, instead of the `output_dir` setting."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print the files written and removed as JSON on stdout.")
    ] = False,
) -> None:
    """Validate the repo, then write the orchestrator files. Writes nothing when the repo is invalid."""
    root = find_repo_root(Path.cwd())
    result = generate_repo(root, output_dir=output)
    if not result.report.ok:
        if json_output:
            typer.echo(json.dumps({"ok": False, "problems": [p.to_json() for p in result.report.problems]}, indent=2))
            raise typer.Exit(code=1)
        for problem in result.report.problems:
            typer.echo(problem.render(), err=True)
        typer.echo(f"{len(result.report.problems)} problem(s) found; nothing was written", err=True)
        raise typer.Exit(code=1)
    if json_output:
        document = {
            "output_dir": str(result.output_dir),
            "files": [path.as_posix() for path in result.files],
            "committed": [path.as_posix() for path in result.committed],
            "removed": [path.as_posix() for path in result.removed],
        }
        typer.echo(json.dumps(document, indent=2))
        return
    for path in result.files:
        typer.echo(f"wrote {result.output_dir / path}")
    for path in result.committed:
        typer.echo(f"wrote {root / path}")
    for path in result.removed:
        typer.echo(f"removed {root / path}")
    count = len(result.files) + len(result.committed)
    typer.echo(
        f"ok: {count} file(s) written ({len(result.files)} to {result.output_dir}), {len(result.removed)} removed"
    )
