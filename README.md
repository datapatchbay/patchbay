<h1>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo/datapatchbay-logo-dark.svg">
    <img alt="datapatchbay" src="assets/logo/datapatchbay-logo-light.svg" width="480">
  </picture>
</h1>

Data products as code. Declare owners, ports and freshness in YAML, then scaffold, validate and generate from one lightweight CLI.

Documentation: [datapatchbay.dev](https://datapatchbay.dev)

## Building the docs

The docs are Sphinx with the Furo theme, managed with [uv](https://docs.astral.sh/uv/):

```sh
uv run --group docs sphinx-build -b html docs docs/_build/html
```

Every push to `main` deploys them to GitHub Pages.
