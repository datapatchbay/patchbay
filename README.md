<h1>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo/datapatchbay-logo-dark.svg">
    <img alt="datapatchbay" src="assets/logo/datapatchbay-logo-light.svg" width="480">
  </picture>
</h1>

Data products as code. Declare owners, ports and freshness in YAML, then scaffold, validate and generate from one lightweight CLI.

Documentation: [datapatchbay.dev](https://datapatchbay.dev)

## Development

The project is managed with [uv](https://docs.astral.sh/uv/). `uv sync` creates `.venv` with the package and the dev tools; tests use pytest, ty checks the types and ruff lints and formats:

```sh
uv sync
uv run pytest     # tests
uv run ty check   # type check
uv run ruff check # lint
uv run ruff format --check  # formatting (drop --check to fix)
```

Tests mirror the package: the tests for `src/datapatchbay/x.py` live in `tests/datapatchbay/test_x.py`. See [CODING_STANDARDS.md](CODING_STANDARDS.md) for the rest. Every pull request runs the tests on Python 3.12, 3.13 and 3.14, and runs ty and ruff.

## Building the docs

The docs are Sphinx with the Furo theme:

```sh
uv run --group docs sphinx-build -b html docs docs/_build/html
```

Every push to `main` deploys them to GitHub Pages.
