# Contributing

datapatchbay is developed in the open at [github.com/datapatchbay/patchbay](https://github.com/datapatchbay/patchbay), under the Apache 2.0 license.

## Report a bug or propose a change

Bugs, questions and proposals go to the [GitHub issues](https://github.com/datapatchbay/patchbay/issues). For a bug, include the command, its output and the files it names. For a larger change, open an issue before you write code, so the design can be agreed first.

## Set up

The project is managed with [uv](https://docs.astral.sh/uv/). `uv sync` creates `.venv` with the package and the development tools:

```sh
git clone https://github.com/datapatchbay/patchbay
cd patchbay
uv sync
uv run dpb --help
```

## Check your change

Run the same four checks as CI before you push:

```sh
uv run pytest                # tests
uv run ty check              # types
uv run ruff check            # lint
uv run ruff format --check   # formatting; drop --check to fix
```

CI runs the unit tests on Python 3.12, 3.13 and 3.14, ty and ruff. The integration tests need Docker and run with `scripts/integration-tests` (ADR-0020): they apply the generated SQL to a real Postgres, run `dbt parse` on the generated dbt files, load the generated DAGs in Airflow 3, and run the example repo end to end. Run them before pushing a change to the Postgres SQL, the generated DAGs or the generated dbt files.

## Follow the standards

- Python code and tests follow [`CODING_STANDARDS.md`](https://github.com/datapatchbay/patchbay/blob/main/CODING_STANDARDS.md). Tests mirror the package: the tests of `src/datapatchbay/x.py` are in `tests/datapatchbay/test_x.py`; the support for one technology is a folder of `src/datapatchbay/integrations/` with its tests in `tests/datapatchbay/integrations/` under the same folder name (inside it, a test file may carry the module name with a technology prefix, such as `test_dbt_output.py`). The integration tests are in `tests/integration/`.
- Use the terms of the [glossary](glossary.md) in code, messages and docs. Its source is `GLOSSARY.md` at the repo root.
- Design decisions are recorded in [`docs/adr`](https://github.com/datapatchbay/patchbay/tree/main/docs/adr), one file per decision. Read the ones that touch your change. A change that goes against one needs a new decision record.
- Keep to the [principles](index.md#principles): three dependencies, no connection to the warehouse, and generated files that stand alone.

## Change the docs

The docs are Markdown files in `docs/`, built with Sphinx and the Furo theme. Every page has a link to its source at the top. Build the site locally:

```sh
uv run --group docs sphinx-build -W -b html docs docs/_build/html
open docs/_build/html/index.html
```

`-W` turns a warning, such as a broken link between pages, into an error, as CI does. Every push to `main` deploys the site.

The pages are sorted by what the reader wants to do:

| Section | Holds | Add a page when |
| --- | --- | --- |
| Getting started | The installation and one tutorial | Rarely. Extend the tutorial instead |
| How-to guides | One task per page, as steps | Users ask how to do something |
| Reference | Commands, files, settings and terms | A command or a kind of file is added |
| Explanation | How it works and why | A concept needs more than a paragraph |

A change to a command, a key or a message is not complete until the page that describes it is changed too.
