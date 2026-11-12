# datapatchbay

Data products as code. Declare owners, ports and freshness in YAML, then scaffold, validate and generate from one lightweight CLI.

## Coding standards

Python code and tests follow `CODING_STANDARDS.md`. Before pushing, run `scripts/check`: ruff, ty and the unit tests in parallel, in about ten seconds. The pre-push hook runs it once `git config core.hooksPath .githooks` is set.

`uv run pytest` runs the unit tests only (DuckDB, no server, no Docker). Integration tests (a real Postgres) live in `tests/datapatchbay/integration/` and run with one command, `scripts/integration-tests`, which needs Docker. Run it before pushing a change to the Postgres SQL. CI does not run it.

## Pull requests

Open the pull request, turn on auto-merge and move on. Do not wait for CI:

```sh
gh pr merge --auto --squash
```

GitHub merges it once the `ci ok` check passes, the only check the ruleset on `main` requires. The branch need not be up to date with `main`; CI on `main` after the merge checks the combination. If the command fails, or `gh pr view --json mergeable -q .mergeable` prints `CONFLICTING`, rebase onto `origin/main`, resolve the conflict, push and run the command again. A pull request whose checks fail stays open with auto-merge on, and the push that fixes it merges it.

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues for `datapatchbay/patchbay`, managed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root, created lazily. See `docs/agents/domain.md`.
