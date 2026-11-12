# datapatchbay

Data products as code. Declare owners, ports and freshness in YAML, then scaffold, validate and generate from one lightweight CLI.

## Coding standards

Python code and tests follow `CODING_STANDARDS.md`. Before pushing, run `uv run pytest`, `uv run ty check`, `uv run ruff check` and `uv run ruff format --check`.

`uv run pytest` runs the unit tests only (DuckDB, no server, no Docker). Integration tests (a real Postgres) live in `tests/datapatchbay/integration/` and run with one command, `scripts/integration-tests`, which needs Docker. Run it before pushing a change to the Postgres SQL or to the generated DAGs (it loads them in Airflow 3 and runs the example). CI does not run it.

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues for `datapatchbay/patchbay`, managed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root, created lazily. See `docs/agents/domain.md`.
