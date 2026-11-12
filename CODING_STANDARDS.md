# Python Coding Standards

This document holds the Python coding standards for datapatchbay. It applies to the package source under `src/`, the
tests under `tests/` and Python tooling in the repository, such as `assets/build.py` and `docs/conf.py`.

Tool configuration lives in `pyproject.toml`. When a tool and this document disagree, the configuration is the source
of truth for the exact values, and this document explains the intent behind them. Decisions with a history are recorded
in `docs/adr/`; this document links to them instead of repeating them.

## Requirement Levels

- **MUST** and **MUST NOT** state a requirement.
- **SHOULD** and **SHOULD NOT** state the expected default. A deviation needs a concrete reason, written in the pull
  request or in a code comment.
- **MAY** states an acceptable option, not a preference.

New code and code that is materially changed MUST follow these standards. Do not copy a pattern that breaks them only
because it already exists somewhere in the code.

## Engineering Priorities

When principles compete, use this order:

1. Correctness and a clear CLI and file contract
2. Maintainability and readability
3. Measured performance
4. Typing purity

- Code SHOULD use the most explicit implementation with the clearest data flow, even when it is a little longer.
- Input from files, the command line and environment variables MUST be validated at the boundary. Inside typed code,
  rely on the invariants the boundary established and fail where an invariant is broken.
- Mutation MUST be intentional and visible in the API. Do not make defensive copies without a concrete ownership or
  correctness need.
- A new abstraction SHOULD centralize real policy, remove real duplication or create a stable boundary. Do not add
  abstractions for a second implementation that does not exist yet. The plugin interfaces of ADR-0009 are the planned
  exception.

## Project Constraints

These follow from the product decisions and apply to every change.

- **Three runtime dependencies.** The package depends on Pydantic, Typer and ruamel.yaml only (ADR-0004). A new runtime
  dependency MUST be agreed in an ADR first. Prefer the standard library.
- **No warehouse connection.** `dpb` reads YAML and writes files (ADR-0001). Package code MUST NOT open database or
  network connections and MUST NOT handle warehouse credentials.
- **Generated files stand alone.** Generated DAG files and SQL MUST NOT import datapatchbay or its dependencies
  (ADR-0001). They are built from plain strings; do not add a template engine (ADR-0004).
- **Generated output is deterministic.** The same input files and settings MUST produce byte-identical output. Sort
  anything whose order comes from a set, a dictionary built from the file system or a directory listing.
- **One YAML library.** Read and write YAML with ruamel.yaml only. Code that rewrites a team's files, such as
  `dpb upgrade`, MUST use round-trip mode so comments and key order survive.
- **Strict keys.** Every file model MUST reject unknown keys (`extra="forbid"`) and accept the free-form `meta` map
  (ADR-0011).
- **Plugins through entry points.** Built-in orchestrator, executor, runtime and warehouse support MUST be registered
  through the same entry points as third-party plugins, not imported directly by the core (ADR-0009).
- **Use the glossary.** Names in code SHOULD use the terms in `GLOSSARY.md`: data product, port, reader, naming
  template. A different word for the same concept needs a meaningful difference in meaning.

## Tool-Enforced Style

[ty](https://docs.astral.sh/ty/) is the type checker. Its configuration is `[tool.ty]` in `pyproject.toml`: it checks
`src/` and `tests/` against the oldest supported Python (from `requires-python`) and treats warnings as errors.

```sh
uv run ty check
```

[ruff](https://docs.astral.sh/ruff/) lints and formats `src/` and `tests/`, with a line length of 120. Its
configuration is `[tool.ruff]` in `pyproject.toml`.

```sh
uv run ruff check
uv run ruff format --check
```

- Do not hand-format; run `uv run ruff format` and keep diffs about behavior.
- Code MUST NOT shadow Python built-ins such as `id`, `type`, `list` or `input`.
- Wildcard imports are prohibited.

## Type Annotations

Typing is a design aid, not a goal in itself.

- Package source and tests MUST pass `ty check` with no diagnostics.
- Functions and methods in package source MUST annotate every parameter and the return value. A short lambda or nested
  callback MAY rely on inference.
- Tests SHOULD annotate fixtures and reusable helpers. Test functions themselves need no annotations.
- The package supports Python 3.12 and later. Use the modern syntax: `X | None`, built-in generics (`list[str]`) and
  PEP 695 type parameters (`def first[T](items: Sequence[T]) -> T`, `type Name = ...`) instead of `TypeVar` and
  `TypeAlias`.
- Package source SHOULD NOT use `from __future__ import annotations`. Pydantic models and Typer commands read their
  annotations at runtime.
- Input parameters that are not mutated SHOULD use the narrowest read-only abstraction, such as `Mapping`, `Sequence` or
  `Iterable`, instead of a concrete mutable type.

```python
# Preferred
def resolve_settings(overrides: Mapping[str, Any]) -> Settings: ...


# Avoid when the function does not mutate the argument
def resolve_settings(overrides: dict[str, Any]) -> Settings: ...
```

### Suppressions and Casts

Resolve a type error in this order:

1. Improve the annotations, the protocol, an overload or the design.
2. Use a line-level, rule-specific `# ty: ignore[rule-name]` with a short reason when ty cannot express a valid
   runtime contract. Do not use a bare `# ty: ignore` or `# type: ignore`.
3. Use `cast()` only when it clearly improves readability.
4. Add a runtime check only when runtime validation is required by the meaning of the code.

Code MUST NOT add pass-through helpers or extra assignments only to satisfy a type checker. File-level suppressions are
limited to generated code.

## Models and Validation

The four kinds of file (`datapatchbay.yaml`, `dataproduct.yaml`, `port.yaml` and the table file) are Pydantic models.
The models are the single source of the validation rules and of the published JSON Schema (`dpb schema`).

- A rule that can be expressed on the model MUST live on the model, so it also appears in the JSON Schema.
- Cross-file rules, such as "an input port's `from` names an existing output port", run after every file has been
  loaded. They MUST NOT be hidden inside a single model's validator.
- Validation MUST report all errors at once, not stop at the first one.
- Every validation error MUST name the file and the line. Keep the ruamel.yaml position information until the error is
  reported.
- Settings resolution MUST record where each resolved value came from, so `dpb config` and `dpb describe` can show it
  (ADR-0008).

## CLI

The CLI is Typer. The command is `dpb`.

- A command SHOULD be a thin layer: parse arguments, call a function in the package, render the result. Logic belongs in
  the package where tests can call it without the CLI.
- Machine output, such as `--json`, MUST go to stdout and contain nothing but that output. Progress messages, warnings
  and errors go to stderr.
- The `--json` shape is a public contract. Changing it is a breaking change.
- A command MUST exit with a non-zero code when it fails. A validation failure is a normal result and MUST NOT print a
  traceback.
- With `--no-input`, a command MUST fail with a clear message instead of prompting.

## Public API Design

datapatchbay is a CLI first. Its Python API is the plugin interface, which is not stable in milestone 1 (ADR-0009).

### Function Signatures

- Positional parameters SHOULD be obvious, stable and hard to misorder.
- Optional parameters and parameters likely to change SHOULD be keyword-only.
- A parameter that accepts a fixed set of strings MUST type them as `Literal[...]` or an enum and normalize to the
  canonical type at the boundary.
- `**kwargs` is not a shape for known data. Known data MUST use explicit parameters. Wrappers MUST NOT accept or
  forward keyword arguments they do not use.

### Interfaces

- Behavioral contracts, including the four extension points, SHOULD be `Protocol` classes.
- An abstract base class SHOULD be used only when inheritance provides shared implementation or required runtime
  behavior.
- Composition and inheritance are both acceptable. Choose by substitutability and clarity, not by blanket preference.

### Imports and Exports

- A module that is part of the plugin interface MUST define an explicit `__all__`. Internal modules SHOULD omit it.
- Plugins and documentation MUST import from the public modules, not from private defining modules.

## Exceptions

- Invalid arguments and broken internal state SHOULD raise built-in exceptions such as `TypeError`, `ValueError` or
  `RuntimeError`, at the point of violation.
- Failures the CLI reports to a user, such as a missing file or an unreadable setting, SHOULD use the package's own
  exceptions, derived from one base class, so the CLI can turn them into a message and an exit code.
- A translated exception MUST keep its cause with `raise ... from exc`.
- Code MUST NOT silently swallow an error, return a success-shaped value after a failure or catch broadly without an
  explicit recovery boundary. The CLI entry point is the one place that catches the package base exception.

## Documentation

### Module Docstrings

- Every module in package source MUST start with a short docstring that states its purpose. Test modules MAY omit it.
- Do not keep inventories of the module's contents in the docstring.

### API Docstrings

Public functions, classes and methods MUST use Google-style docstrings.

- The summary uses the imperative mood and ends with a period.
- Explain behavior, constraints, meaningful errors and non-obvious meaning. Do not restate the signature.
- Positional and ordinary parameters go under `Args:`, keyword-only parameters under `Keyword Args:`.
- `Returns:` SHOULD be present when the value means more than its annotation says. Omit it for `None`.
- `Raises:` SHOULD list the exceptions a caller can act on.
- Comments explain intent, invariants and trade-offs. Do not narrate obvious code.

```python
def derive_port_name(template: str, *, prefix: str, name: str) -> str:
    """Render an output port name from a naming template.

    Args:
        template: The naming template from `datapatchbay.yaml`, for example `"{prefix}_{name}"`.

    Keyword Args:
        prefix: The prefix of the data product's kind, for example `"sa"`.
        name: The data product's bare name, for example `"jaffle_orders"`.

    Returns:
        The port name, which is always snake_case.

    Raises:
        ValueError: If the template refers to a field other than `prefix` and `name`.
    """
```

User-facing documentation lives in `docs/` and is published to datapatchbay.dev. A change to a command, a file or a
setting MUST update the matching page in the same pull request.

## Performance

- Avoid obvious repeated expensive work, such as reading or parsing the same file twice in one command.
- A micro-optimization that hurts readability SHOULD be backed by a measurement.
- Cache only repeated expensive work with stable inputs and a clear lifetime. A cached mutable value MUST NOT be
  handed to callers who could change it.

## Testing

pytest is the only test framework. Tests are behavior-first; coverage is a backstop, not the goal.

- Tests MUST check the observable contract: the files written, the output printed, the exit code, the errors reported.
  They MUST NOT mirror implementation details.
- Every new branch, error path and edge case that matters MUST be covered.
- Tests are plain functions using `assert`. Do not subclass `unittest.TestCase` and do not use the `unittest`
  assertion methods. Use `pytest.raises`, `pytest.mark.parametrize`, `tmp_path` and `monkeypatch`.
- Do not add a pytest plugin without a concrete need that pytest itself cannot meet.
- Test names SHOULD describe the behavior and the condition, for example
  `test_validate_reports_unknown_key_with_line_number`.
- Tests MUST NOT touch the network or the developer's own files. Build repositories of data product files in
  `tmp_path`.
- Tests of generated output SHOULD compare against the complete expected text, so any change shows up as a diff.

### Mocks

Every test brings its own mocks. A test MUST pass on its own, in any order and with no network, no installed plugins
and no settings from the developer's machine.

- A mock MUST be created inside the test or by a fixture the test requests, and MUST be undone when the test ends.
  Use `monkeypatch` for attributes, environment variables and the working directory; it restores them automatically.
  Never patch at import time or in module-level code.
- Mocks SHOULD be small hand-written fakes: a class that implements the same `Protocol` as the real object and records
  what it was asked to do. A fake used by one test file lives in that file. A fake used by several lives in a helper
  module under `tests/` and is imported explicitly.
- Do not add a mocking library such as `pytest-mock`. Use `unittest.mock` only when a fake would be much longer, and
  then with `create_autospec` so the mock keeps the real signature.
- Mock only the boundaries datapatchbay does not own: entry point discovery, environment variables, the clock and
  subprocesses. Do not mock datapatchbay's own modules; test them through their real code.
- Do not mock the file system. Write real files to `tmp_path` and read the result back.
- An `autouse` fixture MUST NOT install a mock that a test cannot see in its own signature, with one exception: a
  top-level `conftest.py` MAY isolate every test from the developer's environment, for example by clearing
  datapatchbay environment variables.

```python
class FakeWarehouse:
    """Record each grant instead of rendering SQL for a real warehouse."""

    def __init__(self) -> None:
        self.grants: list[tuple[str, str]] = []

    def render_grant(self, role: str, view: str) -> str:
        self.grants.append((role, view))
        return f"-- grant {view} to {role}"


def test_generate_grants_each_reader(tmp_path, monkeypatch):
    warehouse = FakeWarehouse()
    monkeypatch.setattr(plugins, "load_warehouse", lambda name: warehouse)
    ...
```

### Test Layout

The tests mirror the package under `src/`. To find the tests of a module, replace `src/` with `tests/` and prefix the
file name with `test_`:

| Source | Tests |
| --- | --- |
| `src/datapatchbay/__init__.py` | `tests/datapatchbay/test_init.py` |
| `src/datapatchbay/models.py` | `tests/datapatchbay/test_models.py` |
| `src/datapatchbay/cli/validate.py` | `tests/datapatchbay/cli/test_validate.py` |

- A test file MUST cover the module it mirrors. A test that exercises several modules, such as a full `dpb generate`
  run, belongs with the module that is its entry point.
- Test directories MUST NOT contain `__init__.py`. pytest runs with `--import-mode=importlib`, so test files in
  different directories may share a name.
- A file named `test_*.py` MUST contain tests. A helper module MUST have another name.

### Fixtures and Helpers

- Shared fixtures MUST live in a `conftest.py`, at the level of the directory that uses them.
- Reusable setup with parameters SHOULD be a fixture that returns a factory function.
- Fixtures MUST be used through pytest injection, never imported from `conftest.py`.
- Helpers that are not fixtures MUST live in a normal module and be imported explicitly.
- Fixture names SHOULD describe what they provide, such as `repo`, `data_product` or `cli`.

### Running the Tests

```sh
scripts/check                      # ruff, ty and the unit tests; extra arguments go to pytest
```

It runs `uv run pytest -n auto`: pytest-xdist spreads the tests over every core, which halves the run. Tests MUST
therefore pass in parallel as well as alone. Plain `uv run pytest` still runs serially, which suits debugging one test.
The integration tests also run serially, because they share Postgres roles. The pre-push hook in `.githooks` runs
`scripts/check`; enable it once per clone with `git config core.hooksPath .githooks`.

Every pull request runs ruff, ty and the unit tests on each supported Python version (`.github/workflows/ci.yml`). A
pull request that only changes the docs site skips them. The ruleset on `main` requires the `ci ok` job, which passes when every other job passed or was skipped.

### Unit Tests and Integration Tests

There are two kinds of test (ADR-0020):

- **Unit tests** run with `uv run pytest`, in CI and on every developer's machine. They need no network, server or
  Docker. The SQL that `dpb` generates is run against DuckDB in the test process.
- **Integration tests** need a real service: a Postgres server, and Airflow in a container next to it. They live
  in `tests/datapatchbay/integration/`, one file per tool or area, and every test in that folder carries the `integration`
  marker automatically (`conftest.py` adds it). `uv run pytest` deselects that marker. Put a new integration test in
  that folder; do not mark tests elsewhere.

One command runs the integration tests. It starts Postgres in Docker, runs them, stops the container and exits non-zero
when a test fails. It needs Docker and nothing else:

```sh
scripts/integration-tests          # extra arguments go to pytest, for example -k audit
```

The same command installs the `dbt` dependency group and runs the tests marked `dbt`, which run the real `dbt parse` on
the generated dbt files. It also loads the generated DAGs in Airflow 3 and runs the example repo end to end, in a
container. Those tests live in the integration folder too, and a missing dbt fails them instead of skipping them. A
selected integration test MUST run.

Run it before pushing a change to the Postgres SQL, to the generated DAGs or to the generated dbt files (properties,
sources, tests, `dbt_project.yml`). CI does not run integration tests. A quality rule MUST also be checked on DuckDB by
a unit test, so that CI keeps covering it.

## Related Guidance

- [Product document](product.md)
- [Glossary](GLOSSARY.md)
- [Architecture decision records](docs/adr/)
