# Settings

The [file reference](files.md#datapatchbayyaml) lists every setting of `datapatchbay.yaml` with its default. This page explains how settings get their value: the defaults, the four levels, and the plugins that the settings name.

## Defaults ship with the package

Every setting has a default inside the package, in one file with the same shape as `datapatchbay.yaml`. Your repo's `datapatchbay.yaml` holds only the changes, and is merged over the defaults:

- maps merge key by key
- lists and single values replace

A small team can start with a one-line root file. Because lists replace, a team can also remove a default kind or domain.

A change to a packaged default changes the behaviour of every repo that didn't set that value. Such a change counts as breaking and comes with a schema version bump.

`dpb config` prints the effective settings and where each one comes from.

## Settings cascade

These settings can be set at four levels: root, data product, port and table. The nearest one wins.

| Setting | Meaning |
| --- | --- |
| `executor` | The technology that builds a table: `python` or `dbt` |
| `runtime` | Where the build code runs: `worker`, `docker` or `kubernetes` |
| `image` | The container image, for the `docker` and `kubernetes` runtimes |
| `container` | Free-form arguments for the container task |
| `severity` | The default severity of quality rules |

The root level is `datapatchbay.yaml` over the packaged defaults. On a data product or a port, write the setting as a key in `dataproduct.yaml` or `port.yaml`. On a table, write it in the `build` block.

```yaml
# dataproduct.yaml
runtime: docker
image: registry.example.com/jaffle-shop:1
```

```yaml
# a table file
build:
  entrypoint: src/orders.py:build
  image: registry.example.com/orders:2   # this table only
```

`orchestrator` can be set at root or data product level only, because one data product is one generated file. On a port or a table, `dpb validate` fails.

`dpb describe` prints the resolved settings of one data product, with the level (`table`, `port`, `dataproduct`, `root` or `defaults`) each value came from.

## `executor` and `runtime`

`executor: dbt` makes a table a dbt model instead of a Python function. See the [dbt reference](dbt.md).

`executor` and `runtime` name plugins, so the files accept any name. `dpb validate` and `dpb generate` check that a plugin of that name is installed, and name the data product and table when it is not.

A runtime that runs an image needs one: `dpb validate` fails when `runtime` is `docker` or `kubernetes` and no level sets `image`. [Run build code in a container](howto/containers.md) shows the steps.

## `container`

`container` is a map that `dpb` hands to the Docker or Kubernetes task as written, without reading it. A team uses it to set environment variables, secrets, a namespace or resource limits.

```yaml
# a table file
build:
  entrypoint: src/orders.py:build
  runtime: docker
  image: registry.example.com/orders:2
  container:
    environment: {PGHOST: warehouse.example.com}
    mem_limit: 1g
```

- The nearest `container` wins as a whole. Maps at different levels are not merged.
- Values must be plain YAML values.
- The arguments are written sorted by name, so the generated file does not depend on their order in YAML.
- `dpb` refuses a key that it sets itself: `task_id`, `image`, `entrypoint` and `command` for Docker, and `task_id`, `name`, `image`, `cmds` and `arguments` for Kubernetes.
- `dpb` passes no credentials. Airflow renders templates in `environment` and `env_vars`, so `PGPASSWORD: "{{ conn.warehouse.password }}"` reads the orchestrator's connection.

## `connection` and `output_dir`

`connection` names the orchestrator's connection to the warehouse, `warehouse` by default. `dpb` only writes the name into the generated files. See [Connections](generated.md#connections).

`output_dir` is the folder `dpb generate` writes to, relative to the repo root. It defaults to `generated`. `dpb generate --output` overrides it.

## The `dbt` settings

`dbt.project_dir`, `dbt.profiles_dir` and `dbt.manifest` are set in `datapatchbay.yaml` only. See [The `dbt` settings](dbt.md#the-dbt-settings).

## Plugins

`orchestrator`, `executor`, `runtime` and `warehouse` each name a plugin. These are built in:

| Setting | Built in | Default |
| --- | --- | --- |
| `orchestrator` | `airflow` (Airflow 3), `dagster`, `local` | `airflow` |
| `executor` | `python`, `dbt` | `python` |
| `runtime` | `worker`, `docker`, `kubernetes` | `worker` |
| `warehouse` | `postgres`, `duckdb` | `postgres` |

Not every combination works:

- `dagster` and `local` support the `worker` runtime only. `dpb generate` fails for a table on `docker` or `kubernetes`. See [Run on Dagster](howto/dagster.md) and [Run a data product without an orchestrator](howto/local.md).
- Tables built by dbt run on the `worker` runtime only.
- `duckdb` enforces no access: it writes the audits and the views of the output ports, but no masking by role and no grants. See [Views and grants](generated.md#views-and-grants).

Plugins are found through Python entry points, and the entry point name is the name used in the settings. A team can install a package that adds one. The plugin interface is not declared stable yet. See [Writing a plugin](plugins.md).

## Settings that a plugin declares

A plugin of any of the four extension points may add settings of its own, so that its configuration lives in `datapatchbay.yaml` next to the rest and is validated, documented and shown like it ([ADR-0025](https://github.com/datapatchbay/patchbay/blob/main/docs/adr/0025-plugins-declare-their-own-settings.md)):

- A **section** at the root of `datapatchbay.yaml`, named after the plugin (its entry point name). The plugin owns the model of the section, with a description for every key, and its defaults. A section is read at the root only and does not cascade. The `dbt:` block is the section of the `dbt` plugin.
- **Naming templates** under `conventions.names`, with placeholders of their own. `dbt_model` is a naming template of the `dbt` plugin.

Both are merged over the plugin's defaults like any setting: maps merge key by key, and a value in `datapatchbay.yaml` replaces the default. `dpb config` lists them, and says where each value comes from: `(defaults of plugin dbt)` or `(datapatchbay.yaml)`. `dpb schema root` includes the sections and templates of the installed plugins, so an editor completes them.

A section is valid only when an installed plugin declares it. Any other root key fails `dpb validate` as an unknown key, and says that no installed plugin declares a settings section of that name; install the plugin or fix the typo. A plugin whose name is also a setting of datapatchbay (`runtime`, `conventions`, ...), or whose section or template another plugin declares too, is refused with an error. Existing repos are not affected: the file format and the schema version stay as they were. [Writing a plugin](plugins.md#declare-settings-and-naming-templates) shows how a plugin declares them.
