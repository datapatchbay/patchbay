# Why not just dbt, and other alternatives

Most teams that look at datapatchbay already have a warehouse, dbt and some layering of tables. This page says what those leave open, how other tools compare, and when datapatchbay is the wrong choice.

## Why dbt and a warehouse are not enough

Many teams start with dbt on a warehouse, and it works well for building tables. dbt is a build tool, though. It knows models, not products:

- **Every model is public by default.** Any model can `ref()` any other, so a report joins into an intermediate model, and the next refactor breaks it.
- **Ownership is optional.** dbt has groups, access levels, model contracts and grants. Each one is opt-in, per model, and nothing checks that the whole project uses them the same way.
- **dbt sees only dbt.** Ingestion in Python, a BI tool or an AI agent that queries the warehouse are outside the project. dbt does not know who reads a model, so it cannot tell the owner who breaks when it changes.
- **Access lives somewhere else.** Grants and masking of personal data are written by hand in the warehouse, or not at all. Nobody reviews them next to the code that builds the data.
- **Freshness is checked on sources, not promised on outputs.** A consumer cannot see how old the data in a model may be.

## Why a medallion architecture is not enough

A medallion architecture sorts tables into layers by processing stage: bronze for raw, silver for cleaned, gold for ready to use. It answers how clean a table is, not who owns it or who may read it:

- **Layers cut across owners.** One gold layer holds the tables of every domain, and nobody owns the layer. When a number is wrong, there is still no name to call.
- **Silver leaks.** When gold lacks a column, consumers read silver, and the cleaned-but-internal tables become a public interface by accident.
- **A layer makes no promise.** Gold says nothing about freshness, quality rules or readers of a single table.
- **One central team runs all layers.** Every new source and every change waits for that team.

## What datapatchbay adds to them

datapatchbay does not replace dbt or the layers. It cuts the platform vertically into data products, and keeps the layers inside each one: bronze and silver are the private schema of a data product, and gold is its output port. The difference is that each data product has its own gold, with its own owner, readers and promises.

dbt stays the build tool where a team wants it. Python and dbt build code sit side by side, per table, so ingestion, dbt models and readers are in one model. For a table built by dbt, `dpb generate` writes the dbt properties from the table file: an enforced model contract, the quality rules as data tests, a dbt group with the owner, and a `source()` for every output port the data product reads. What dbt leaves opt-in per model, `dpb validate` checks for every data product in CI. See [Build a table with dbt](howto/dbt.md) and [Import an existing dbt project](howto/import-dbt.md).

## Other tools

| Alternative | What it gives you | Where it stops |
| --- | --- | --- |
| Internal cookiecutter | A scaffold that matches house style | Runs once, then drifts. No check, no list, no upgrade path |
| Open Data Product Specification, Data Contract Specification | A shared vocabulary | Large schemas with no workflow. Hard to start with |
| datacontract-cli | Contract validation | No scaffolding, no ownership model, nothing that generates the orchestrator or warehouse files |
| dbt mesh features | Cross-project refs and model contracts | Tied to dbt, and to its paid platform for the multi-project part |
| dbt-project-evaluator, dbt-checkpoint | Linting of names and structure | dbt only, and no notion of a product or an owner |
| Data Product Portal (Dataminded) | Web marketplace with access requests and governance | A running service with a database, built for scale. Complementary: datapatchbay could feed it |

The real competitor is the first row. Most teams build that cookiecutter themselves and stop there.

## When not to use datapatchbay

- **Your warehouse is not Postgres.** Postgres is the only warehouse with views, masking and grants today. A warehouse is a [plugin](plugins.md), but that interface is not stable yet.
- **You run Airflow 2.** The generated DAGs need Airflow 3. Dagster and the local script are the other orchestrators.
- **One person builds everything in one dbt project.** Ownership, readers and ports pay off when a second person or team builds on the same warehouse.
- **You need a catalog that people browse.** There is no web UI, no search across the company and no workflow for access requests. Approvals are pull requests.
- **You need freshness that is measured.** `dpb validate` checks the promise against the schedules in the files. Nothing measures the data. See [Limits and guarantees](limits.md).
- **Your data products live in many repos.** datapatchbay reads one repo, and a data product can only read an output port of the same repo.
