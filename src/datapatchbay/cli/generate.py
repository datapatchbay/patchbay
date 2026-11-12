"""The `dpb generate` command."""

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
) -> None:
    """Validate the repo, then write the orchestrator files. Writes nothing when the repo is invalid."""
    result = generate_repo(find_repo_root(Path.cwd()), output_dir=output)
    if not result.report.ok:
        for problem in result.report.problems:
            typer.echo(problem.render(), err=True)
        typer.echo(f"{len(result.report.problems)} problem(s) found; nothing was written", err=True)
        raise typer.Exit(code=1)
    for path in result.files:
        typer.echo(f"wrote {result.output_dir / path}")
    typer.echo(f"ok: {len(result.files)} file(s) written to {result.output_dir}")
