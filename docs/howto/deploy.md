# Deploy the generated DAGs

`dpb generate` writes one Airflow 3 DAG file per data product. This guide shows how to generate them in CD, how to get them to Airflow, and what Airflow needs to run them.

## Generate in CD

Generated DAG files are build output. Do not commit them: generate them on every deploy, from the commit you deploy.

```sh
rm -rf generated
dpb generate
```

- `dpb generate` validates first. When anything is wrong it prints the problems, writes nothing and exits 1, so a broken repo does not deploy.
- Remove the output folder first. `dpb generate` does not remove the file of a data product that no longer exists, and `dpb validate` fails on such a file in the default output folder.
- The same input gives byte-identical files, so a deploy without changes changes nothing.

The files go to the folder of the `output_dir` setting, `generated` by default. `--output <folder>` writes somewhere else.

## Deploy the repo and the generated files together

A table on the `worker` runtime runs its build code on the Airflow worker. The generated DAG file finds that code from its own location. It holds the relative path from the output folder to the data product folder, as it was when you ran `dpb generate`: `../dataproducts/<data product>` for the default output folder. So the output folder and the data product folders must keep their relative places on the worker.

The simplest way is to deploy the whole repo, with `generated/` in it, as the DAG bundle. A DAG bundle is the place where Airflow 3 reads DAG files from:

```text
<DAG bundle>/
  datapatchbay.yaml
  dataproducts/
    sa_jaffle_orders/
      src/orders.py        the DAG loads this file
  generated/
    sa_jaffle_orders.py    the DAG file
```

Tables on the `docker` or `kubernetes` runtime do not read the repo on the worker. Their build code is in the image. See [Run build code in a container](containers.md).

## Get the files to Airflow

`generated/` is not in git, so the CD job has to bring it to Airflow together with the repo. Generate first, then publish the checkout in the way your Airflow reads DAG files:

A folder that Airflow reads
: Copy the checkout, with `generated/` in it, to the folder of the DAG bundle on the Airflow hosts, or to the bucket that the bundle reads:

  ```sh
  rm -rf generated
  dpb generate
  rsync -a --delete --exclude .git ./ airflow:/opt/airflow/dags/jaffle_shop/
  ```

The Airflow image
: Copy the checkout, with `generated/` in it, into the image that the scheduler and the workers run.

A git DAG bundle
: A bundle that tracks the source repo does not see `generated/`. Let the CD job commit the checkout, with `generated/` in it, to a deploy branch or a deploy repo, and point the bundle at that.

Whichever way you choose, the workers must see the same files as the DAG processor, because the build tasks load the build code on the worker.

## What Airflow needs

Provider packages
: `apache-airflow-providers-common-sql` and the provider of your warehouse. `apache-airflow-providers-docker` or `apache-airflow-providers-cncf-kubernetes` for those runtimes. Not datapatchbay: the DAG files do not import it.

A connection to the warehouse
: The audits, views and grants run through an Airflow connection. Its name is the `connection` setting, `warehouse` by default. `dpb` only writes the name into the DAG file. You create the connection in Airflow.

The roles
: The generated SQL grants access to the roles of the readers, the PII readers and the reading data products (`dp_<data product>` by default). It never creates a role. Create them in the warehouse first, usually through your identity provider or an infrastructure repo.

Build code that can connect
: Build code connects to the warehouse by itself. On the `worker` runtime it can use the Airflow connection. In a container it uses what you put in the container's environment.

dbt, for tables built by dbt
: The `dbt` command and a profile on the worker, and the `dbt_project.yml` of the repo in the DAG bundle. See [dbt on the worker](../dbt.md#dbt-on-the-worker).

## When a change takes effect

A merged change does nothing by itself. It takes effect when the new DAG file is deployed and the DAG runs:

- A data product with a source input port runs on that port's `schedule`.
- A data product that reads another data product runs when that output port is updated.
- A change to readers is applied by the `apply_access` task of the next run. To apply it sooner, trigger the DAG.

## Check a deploy

- The DAG is named after the data product folder and carries the tag `datapatchbay`.
- Each table has a `build_<table>` task, and an `audit_<table>` task when it has quality rules. The DAG ends with `apply_access` and `publish_outputs`.
- When `apply_access` fails on a missing role, the message names the role, and the views and grants of the previous run stay in place.
