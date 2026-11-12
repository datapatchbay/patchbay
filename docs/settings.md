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
- the container image
- the default `severity`

`orchestrator` can be set at root or data product level only, because one data product is one DAG.

`dpb config` prints the effective settings and where each one comes from. `dpb describe` does the same for one data product.

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
