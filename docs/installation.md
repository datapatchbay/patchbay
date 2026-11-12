# Installation

datapatchbay is one Python package with one command, `dpb`. It needs Python 3.12 or newer and has three dependencies: Pydantic, Typer and ruamel.yaml.

It is not on PyPI yet, so every way of installing it below reads from GitHub.

## Install the command

With [uv](https://docs.astral.sh/uv/), install `dpb` as a tool. It gets its own environment, and the command is on your `PATH`:

```sh
uv tool install git+https://github.com/datapatchbay/patchbay
```

Check that it works:

```console
$ dpb --help
```

## Other ways

Run it once without installing it
: ```sh
  uvx --from git+https://github.com/datapatchbay/patchbay dpb validate
  ```

Add it to a project
: A repo that already has a `pyproject.toml` can list datapatchbay as a development dependency. The lock file then holds the exact commit, so CI and every engineer run the same `dpb`.

  ```sh
  uv add --dev git+https://github.com/datapatchbay/patchbay
  uv run dpb validate
  ```

Install it with pip
: ```sh
  pip install git+https://github.com/datapatchbay/patchbay
  ```

## What you do not need

`dpb` reads YAML and writes files. It never connects to the warehouse or to the orchestrator. On the machine where you run `dpb`, you need no Airflow, no database driver and no credentials. You need dbt only when tables are built by dbt: `dpb validate` then reads the manifest that `dbt parse` writes.

## What the orchestrator needs

The generated DAG files do not import datapatchbay, so do not install it on Airflow. They need Airflow 3 and these provider packages:

| Package | Needed for |
| --- | --- |
| `apache-airflow-providers-common-sql` | The audits, views and grants |
| The provider of your warehouse, such as `apache-airflow-providers-postgres` | The connection that runs them |
| `apache-airflow-providers-docker` | Tables with `runtime: docker` |
| `apache-airflow-providers-cncf-kubernetes` | Tables with `runtime: kubernetes` |

A data product with tables built by dbt also needs the `dbt` command on the worker. See [dbt on the worker](settings.md#dbt-on-the-worker).

## Upgrade

Install again from GitHub to get the newest commit:

```sh
uv tool install --reinstall git+https://github.com/datapatchbay/patchbay
```

After an upgrade:

1. Run `dpb upgrade`. It rewrites your files when the schema version changed, and says so when there is nothing to do.
2. Save the JSON Schemas again if your editor uses them. See [Set up your editor](howto/editor.md).

## Uninstall

```sh
uv tool uninstall datapatchbay
```

The generated files keep working without datapatchbay, because they do not import it.

## Next

Follow the [tutorial](tutorial.md) to create your first data product.
