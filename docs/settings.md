# Settings and plugins

## Defaults ship with the package

Every setting has a default inside the package, in one file with the same shape as `datapatchbay.yaml`. Your repo's `datapatchbay.yaml` holds only the changes, and is merged over the defaults:

- maps merge key by key
- lists and single values replace

A small team can start with a one-line root file. Because lists replace, a team can also remove a default kind or domain.

A change to a packaged default changes the behaviour of every repo that didn't set that value. Such a change counts as breaking and comes with a schema version bump.

## Settings cascade

These settings can be set at four levels: root, data product, port and table. The nearest one wins.

- `executor`
- `runtime`
- `image`, the container image for container runtimes
- the default `severity`

The root level is `datapatchbay.yaml` over the packaged defaults. On a data product or a port, write the setting as a key in `dataproduct.yaml` or `port.yaml`. On a table, write it in the `build` block.

```yaml
# dataproduct.yaml
runtime: docker
image: registry.example.com/lab:1
```

```yaml
# a table file
build:
  entrypoint: src/orders.py:build
  image: registry.example.com/orders:2   # this table only
```

`executor` and `runtime` name plugins, so the files accept any name. `dpb validate` and `dpb generate` check that a plugin of that name is installed, and name the data product and table when it is not.

`orchestrator` can be set at root or data product level only, because one data product is one DAG. On a port or a table, `dpb validate` fails.

`dpb config` prints the effective settings and where each one comes from. `dpb describe` does the same for one data product, with the level (`table`, `port`, `dataproduct`, `root` or `defaults`) each resolved value came from.

## Plugins

datapatchbay has four extension points:

| Extension point | Built in |
| --- | --- |
| Orchestrator | Airflow 3 |
| Executor | Python |
| Runtime | Worker (Docker and Kubernetes follow) |
| Warehouse | Postgres |

Plugins are found through Python entry points, so plugin support adds no dependency. The built-in support is written against the same interfaces and registered the same way. A plugin package registers a class, or a function without arguments that returns the plugin, in one of four groups, and the entry point name is the name used in the settings:

```toml
[project.entry-points."datapatchbay.orchestrators"]
airflow = "datapatchbay.builtin.airflow:AirflowOrchestrator"
```

The groups are `datapatchbay.orchestrators`, `datapatchbay.executors`, `datapatchbay.runtimes` and `datapatchbay.warehouses`. The interfaces are the `Protocol` classes in `datapatchbay.plugins`. The orchestrator composes the DAG from what the others contribute: the executor says what to call, the runtime renders the build task, and the warehouse returns SQL tasks that the orchestrator runs through its own connection.

The plugin interface is not stable in milestone 1. It is declared stable once the dbt executor, the first second implementation of an extension point, has proven it.

## Where the generated files go

`output_dir` in `datapatchbay.yaml` is the folder `dpb generate` writes to, relative to the repo root. It defaults to `generated`. `dpb generate --output` overrides it.
