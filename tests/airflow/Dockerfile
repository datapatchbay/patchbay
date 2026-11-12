# The Airflow of the integration tests (ADR-0020): Airflow 3 with the providers the generated DAGs use, and dbt in a
# separate virtual environment because dbt-postgres conflicts with Airflow's pins. datapatchbay is not installed here, so
# a generated DAG file has to stand alone (ADR-0001). The Airflow version is pinned here and nowhere else.
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

ARG PYTHON_VERSION
ARG AIRFLOW_VERSION=3.4.0
ARG DBT_POSTGRES_VERSION=1.10

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/airflow \
    && /opt/airflow/bin/pip install \
        "apache-airflow==${AIRFLOW_VERSION}" \
        apache-airflow-providers-common-sql \
        apache-airflow-providers-docker \
        apache-airflow-providers-cncf-kubernetes \
        apache-airflow-providers-postgres \
        --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

RUN python -m venv /opt/dbt \
    && /opt/dbt/bin/pip install "dbt-postgres>=${DBT_POSTGRES_VERSION}"

# The scripts run Airflow commands through the PATH; the `dbt` command is found through the folder the scripts are given.
ENV PATH=/opt/airflow/bin:$PATH
