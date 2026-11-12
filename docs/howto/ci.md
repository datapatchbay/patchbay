# Validate in CI

Run `dpb validate` on every pull request, so a broken contract never reaches `main`. It needs no warehouse, no orchestrator and no credentials: it only reads the files in the repo. A repo with tables built by dbt runs `dbt parse` first (see [Repos with dbt](#repos-with-dbt)).

## GitHub Actions

Add `.github/workflows/dataproducts.yml`:

```yaml
name: data products

on:
  pull_request:
  push:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.3.3
      - name: Validate the data products
        run: uvx --from git+https://github.com/datapatchbay/patchbay dpb validate
```

Then make the `validate` job a required check of the `main` branch.

## Use the same version everywhere

The workflow above installs the newest commit on each run. To pin one, add the commit to the URL:

```sh
uvx --from git+https://github.com/datapatchbay/patchbay@<commit> dpb validate
```

If the repo has a `pyproject.toml`, add datapatchbay as a development dependency instead. The lock file then pins it for CI and for every engineer:

```sh
uv add --dev git+https://github.com/datapatchbay/patchbay
```

```yaml
      - name: Validate the data products
        run: uv run --locked dpb validate
```

## Read the result

`dpb validate` looks for `datapatchbay.yaml` in the working directory and its parents, so run it from anywhere inside the repo.

It exits 0 when every file is valid, and the job passes. It exits 1 when there are problems: each one is a line `file:line: message` on stderr, and all of them are reported at once. It exits 2 when it could not start the check, for example because there is no `datapatchbay.yaml`.

For a script or an agent, `dpb validate --json` prints one JSON document on stdout, with `ok`, `dataproducts_checked` and a list of `problems`. See [`dpb validate`](../cli.md#dpb-validate).

## Other CI systems

The check is one command with an exit code, so it runs the same on GitLab CI, Azure Pipelines or Jenkins. Install uv, then run the `uvx` command above.

## Also check that generation works

`dpb generate` validates first, then writes the files. Running it in CI proves that every data product also generates. Write to a folder outside the repo:

```yaml
      - name: Generate the DAGs
        run: uvx --from git+https://github.com/datapatchbay/patchbay dpb generate --output "$RUNNER_TEMP/dags"
```

## Repos with dbt

When tables are built by dbt, `dpb validate` reads the dbt manifest to check what the models read. Run `dbt parse` before it. `dbt parse` needs the dbt adapter and a profile, but it does not connect to the warehouse:

```yaml
      - name: Parse the dbt project
        run: uvx --from dbt-core --with dbt-postgres dbt parse
      - name: Validate the data products
        run: uvx --from git+https://github.com/datapatchbay/patchbay dpb validate
```

Without the manifest, `dpb validate` fails and says to run `dbt parse`.

`dpb validate` also fails when a committed dbt file, or the `model-paths` and `test-paths` of `dbt_project.yml`, does not match the table files. The message names the file and says to run `dpb generate`. Run it locally and commit the result. See [Build a table with dbt](dbt.md).

## Let the owner approve changes to a port

A new reader of an output port is a change to that port's `port.yaml`. To make sure that the owner of the data product reviews it, give the folder a code owner. On GitHub, in `.github/CODEOWNERS`:

```text
/dataproducts/sa_jaffle_orders/  @your-org/shop-team
```
