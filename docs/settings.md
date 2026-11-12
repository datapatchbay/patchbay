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

`executor` and `runtime` name plugins, so the files accept any name. Whether a plugin of that name exists is checked once plugins are loaded, not by `dpb validate`.

`orchestrator` can be set at root or data product level only, because one data product is one DAG. On a port or a table, `dpb validate` fails.

`dpb config` prints the effective settings and where each one comes from. `dpb describe` does the same for one data product, with the level (`table`, `port`, `dataproduct`, `root` or `defaults`) each resolved value came from.

## Plugins

datapatchbay has four extension points:

| Extension point | Built in |
| --- | --- |
| Orchestrator | Airflow 3 |
| Executor | Python |
| Runtime | Worker, Docker, Kubernetes |
| Warehouse | Postgres |

Plugins are found through Python entry points, so plugin support adds no dependency. The built-in support is written against the same interfaces and registered the same way.

The plugin interface is not stable in milestone 1. It is declared stable once the dbt executor, the first second implementation of an extension point, has proven it.
