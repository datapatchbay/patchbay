# Run build code in a container

By default a table's build function runs on the Airflow worker. With the `docker` or `kubernetes` runtime it runs in a container, from an image that you build. Use this when the build code needs its own dependencies, or more memory than the worker has.

## 1. Set the runtime and the image

Both settings cascade, so set them where they apply: in `datapatchbay.yaml` for every data product, in a `dataproduct.yaml`, in a `port.yaml`, or in the `build` block of one table.

```yaml
# dataproducts/sa_jaffle_orders/dataproduct.yaml
runtime: docker
image: registry.example.com/jaffle-shop:1
```

`dpb validate` fails when a table resolves to `docker` or `kubernetes` and no level sets `image`.

## 2. Build the image

The container is started as `python -c <loader> <file> <function> <params>`. The loader is a few lines of standard library Python in the generated DAG file. It imports the entrypoint file and calls the function with the table's `params`.

So the image needs three things:

- `python` on the path, with the dependencies of the build code
- the data product folder, which holds the build code
- that folder as its working directory

```dockerfile
FROM python:3.12-slim
RUN pip install "psycopg[binary]"
COPY dataproducts/sa_jaffle_orders /app
WORKDIR /app
```

The image does not need datapatchbay. If the folder is somewhere else in the image, set `working_dir` in `container` (see the next step).

## 3. Pass the connection details

`dpb` passes no credentials. Build code in a container reads what you put in the container's environment. The `container` setting is a map that `dpb` hands to the Airflow task as written:

```yaml
# dataproducts/sa_jaffle_orders/dataproduct.yaml
runtime: docker
image: registry.example.com/jaffle-shop:1
container:
  environment:
    PGHOST: warehouse.example.com
    PGPASSWORD: "{{ conn.warehouse.password }}"
  mem_limit: 1g
```

Airflow renders templates in `environment`, so `{{ conn.warehouse.password }}` reads the password of the Airflow connection `warehouse` when the task runs.

For Kubernetes, the keys are those of the `KubernetesPodOperator`:

```yaml
runtime: kubernetes
image: registry.example.com/jaffle-shop:1
container:
  namespace: data
  env_vars:
    PGHOST: warehouse.example.com
```

- The nearest `container` wins as a whole. Maps at different levels are not merged.
- `container` is written for one operator, so set it at the level where you set the runtime.
- `dpb` refuses a key that it sets itself: `task_id`, `image`, `entrypoint` and `command` for Docker, and `task_id`, `name`, `image`, `cmds` and `arguments` for Kubernetes.

## 4. Install the provider on Airflow

The generated DAG file uses the `DockerOperator` or the `KubernetesPodOperator`:

| Runtime | Package on Airflow |
| --- | --- |
| `docker` | `apache-airflow-providers-docker` |
| `kubernetes` | `apache-airflow-providers-cncf-kubernetes` |

## 5. Generate and check

```console
$ dpb validate
$ dpb describe sa_jaffle_orders
$ dpb generate
```

`dpb describe` shows the resolved `runtime`, `image` and `container` of every table, and the level each value came from.

## What to know

- Tables with different runtimes can sit in one DAG. Set `runtime` on a table's `build` block to move only that table.
- `params` must be plain YAML values, because the loader reads them as JSON. Quote a date.
- Airflow renders the params as templates, so a param may contain `{{ ds }}`.
- Tables built by dbt cannot use a container runtime. They run on the worker.
- Audits, views and grants still run on Airflow, through its connection to the warehouse. Only the build code runs in the container.
