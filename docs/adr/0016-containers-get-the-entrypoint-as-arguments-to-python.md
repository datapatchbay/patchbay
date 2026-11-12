# Containers get the entrypoint and its params as arguments to python

A container runtime (`docker`, `kubernetes`) starts the container with `python -c LOADER FILE FUNCTION PARAMS`. `LOADER` is a few lines of standard library Python that dpb writes into the generated DAG file. It imports `FILE`, a path relative to the container's working directory, and calls `FUNCTION` with `PARAMS`, a JSON string, as keyword arguments. The team builds its image so that `python` is on the path and the working directory is the data product folder, which holds the build code (ADR-0015). We chose this because the image then needs nothing of datapatchbay (ADR-0001), the generated file still stands alone, and the call is the same one the `worker` runtime makes.

dpb sets the image, the entrypoint (`python`) and the arguments. It sets nothing else on the container task. A free-form `container` setting, which cascades like `runtime` and `image`, holds further arguments of the operator, such as `environment` for Docker or `namespace` and `env_vars` for Kubernetes. dpb writes them into the task as written and does not read them. It refuses a `container` key that it sets itself. dpb passes no credentials (ADR-0001): the team supplies them through `container`, for example as Airflow templates such as `{{ conn.warehouse.password }}` in `environment`, or through the image and the cluster.

## Considered options

- **Environment variables** (`PATCHBAY_ENTRYPOINT`, `PATCHBAY_PARAMS`) read by an image entry script. Rejected: the image would need a script that dpb defines, so the team has to copy it into every image and keep it in step.
- **A package that dpb provides**, installed in the image, with a command such as `dpb-run`. Rejected: the image would depend on datapatchbay, which breaks ADR-0001: generated files and the code they run never import datapatchbay.
- **A file mounted into the container.** Rejected: it needs a volume, which Docker and Kubernetes configure differently, and params in a file are no easier to read than arguments.

## Consequences

- The image must have a `python` with the dependencies of the build code, and its working directory must be the data product folder. A team that cannot do that sets `working_dir` in `container` to where the folder is.
- Params must be plain YAML values: the loader reads them as JSON. A date has to be quoted, as for the `worker` runtime.
- Airflow renders the arguments as templates, so a param may contain `{{ ds }}`. The loader itself has no braces, so it is not changed by the template engine.
- The executor is the Python executor. Another executor needs its own way of starting the container.
- `container` is written for one operator. A value that fits `DockerOperator` fails when the same level also applies to a Kubernetes table, so teams set it at the level where the runtime is set.
- A runtime says whether it needs an image (`needs_image`), and `dpb validate` reports a table of such a runtime whose resolved `image` is not set.
