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
- `container`, free-form arguments for the container task of a container runtime
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

`executor: dbt` makes a table a dbt model instead of a Python function; see the table file in `docs/files.md`. `executor` and `runtime` name plugins, so the files accept any name. `dpb validate` and `dpb generate` check that a plugin of that name is installed, and name the data product and table when it is not.

`container` is a map that dpb hands to the Docker or Kubernetes task as written, without reading it, so a team can set environment variables, secrets, a namespace or resource limits. The nearest `container` wins as a whole; maps at different levels are not merged. The arguments are written sorted by name, so the generated file does not depend on their order in YAML. Values must be plain YAML values. dpb refuses a key that it sets itself (`task_id`, `image`, `entrypoint` and `command` for Docker; `task_id`, `name`, `image`, `cmds` and `arguments` for Kubernetes). dpb passes no credentials: Airflow renders templates in `environment` and `env_vars`, so `PGPASSWORD: "{{ conn.warehouse.password }}"` reads the orchestrator's connection.

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

A runtime that runs an image needs one: `dpb validate` fails when `runtime` is `docker` or `kubernetes` and no level sets `image`.

`orchestrator` can be set at root or data product level only, because one data product is one DAG. On a port or a table, `dpb validate` fails.

`dpb config` prints the effective settings and where each one comes from. `dpb describe` does the same for one data product, with the level (`table`, `port`, `dataproduct`, `root` or `defaults`) each resolved value came from.

## dbt on the worker

A data product with tables built by dbt gets one task in its DAG, `build_dbt`, which runs `dbt build --select path:<its models folder>` on the Airflow worker. It runs after the data product's Python tables, so the dbt models can read their output, and before the views and grants. dbt builds the models and runs their data tests in dependency order, so a broken rule with severity `error` fails the task, and dpb generates no audit task for these tables. dpb uses the dbt profile the team already has and manages no connection (ADR-0001).

Two settings, in `datapatchbay.yaml` only, say where dbt is on the worker:

```yaml
dbt:
  project_dir: .        # the dbt project; a relative path is relative to the repo root as deployed with the DAG files
  profiles_dir: ~/.dbt  # the folder with profiles.yml; `~` is the home of the worker's user, a relative path is relative to the dbt project
```

The defaults assume that the repo is deployed to the worker with the DAG files (for example as the DAG bundle), that `dbt_project.yml` is at the repo root, and that dbt and the profile are installed for the worker's user. dbt is run as the `dbt` command of the worker's environment; dpb installs nothing. Authenticate through the profile, for example with environment variables on the worker. If the dbt project sits elsewhere on the worker with the layout of the repo, set an absolute `project_dir`. A relative `project_dir` other than `.` must contain the data product folders.

One more setting is read on the machine that runs `dpb validate`, not on the worker:

```yaml
dbt:
  manifest: target/manifest.json  # the dbt manifest made by `dbt parse`; relative to the repo root
```

`dpb validate` reads this file to check what the dbt models read (see [`dpb validate`](cli.md#dpb-validate)). When the repo has tables built by dbt and the file is missing, validation fails and says to run `dbt parse`. Set it if `dbt parse` writes elsewhere, for example with `--target-path`.

All tables built by dbt in a data product share this one task, so they must resolve to the same `runtime`, and it must be `worker`: `docker` and `kubernetes` fail in `dpb validate` (and so in `dpb generate`) at the line of the table's runtime. A Python table cannot list a dbt table in `needs`, because the Python tables are built first; `dpb validate` reports it at the `needs` line.

## Plugins

datapatchbay has four extension points:

| Extension point | Built in |
| --- | --- |
| Orchestrator | Airflow 3 |
| Executor | Python, dbt |
| Runtime | Worker, Docker, Kubernetes |
| Warehouse | Postgres, DuckDB |

The `duckdb` warehouse writes the audit tasks of quality rules, the same as Postgres. It does not generate views for output ports yet, so a repo with `warehouse: duckdb` gets no `apply_access` task. It is the warehouse that the unit tests of datapatchbay run against (ADR-0020).

Plugins are found through Python entry points, so plugin support adds no dependency. The built-in support is written against the same interfaces and registered the same way. A plugin package registers a class, or a function without arguments that returns the plugin, in one of four groups, and the entry point name is the name used in the settings:

```toml
[project.entry-points."datapatchbay.orchestrators"]
airflow = "datapatchbay.builtin.airflow:AirflowOrchestrator"
```

The groups are `datapatchbay.orchestrators`, `datapatchbay.executors`, `datapatchbay.runtimes` and `datapatchbay.warehouses`. The interfaces are the `Protocol` classes in `datapatchbay.plugins`. The orchestrator composes the DAG from what the others contribute: the executor says what to call, the runtime renders the build task, and the warehouse returns SQL tasks that the orchestrator runs through its own connection.

The plugin interface is not declared stable yet.

## Where the generated files go

`output_dir` in `datapatchbay.yaml` is the folder `dpb generate` writes to, relative to the repo root. It defaults to `generated`. `dpb generate --output` overrides it.
