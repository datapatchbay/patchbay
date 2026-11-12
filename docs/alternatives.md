# Alternatives

| Alternative | What it gives you | Where it stops |
| --- | --- | --- |
| Internal cookiecutter | A scaffold that matches house style | Runs once, then drifts. No check, no list, no upgrade path |
| Open Data Product Specification, Data Contract Specification | A shared vocabulary | Large schemas with no workflow. Hard to start with |
| datacontract-cli | Contract validation | No scaffolding, no ownership model, no deploy |
| dbt mesh features | Cross-project refs and model contracts | Tied to dbt, and to its paid platform for the multi-project part |
| dbt-project-evaluator, dbt-checkpoint | Linting of names and structure | dbt only, and no notion of a product or an owner |
| Data Product Portal (Dataminded) | Web marketplace with access requests and governance | A running service with a database, built for scale. Complementary: datapatchbay could feed it |

The real competitor is the first row. Most teams build that cookiecutter themselves and stop there.
