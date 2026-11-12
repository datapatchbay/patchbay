# What is a data product

This page explains the idea behind datapatchbay for a reader who has never worked with data products: what one is, how `dpb` puts it into files, and where the idea comes from.

## Data as a product

A table that a pipeline writes as a side effect has no owner, no promise and no interface. Whoever needs it joins straight into it, and every change breaks someone. Treating data as a product turns that around. A team publishes data for others on purpose, the way a team publishes an API:

- It has an **owner** who is accountable for it.
- It has **consumers**, and the owner knows who they are. datapatchbay calls them **readers**.
- It has an **interface** that stays stable while the inside changes.
- It makes **promises**, such as a schema, quality rules and freshness, and keeps them.

A **data product** is the unit that carries all of this: the data, the code that builds it, the metadata that describes it and the policies that guard it, owned together.

## A data product in datapatchbay

In datapatchbay a data product is one folder in a repo. The folder holds YAML files that describe the data product, and the code that builds its tables:

```text
dataproducts/sa_jaffle_orders/
  dataproduct.yaml     who owns it, and which ports it has
  inputs/              what it reads: a source, or another data product
  outputs/             what it publishes, to whom, and how fresh
  src/                 the code that builds its tables
```

Data enters and leaves through **ports**. An input port receives data, and an output port publishes it. The readers of a data product see only its output ports, never the tables behind them.

Each part of the idea has a place in the files:

| Problem | What datapatchbay does |
| --- | --- |
| Nobody owns a table | Every data product names an **owner**, and `dpb validate` fails without one. A **technical owner** can be named next to it |
| Everything is public | Build code writes to the data product's **private schema**. Readers see only the views of an **output port**, so the inside can change freely |
| Unknown consumers | A data product that reads another one must be listed in the **readers** of the output port, so the owner approves every new reader in a pull request |
| Access by hand | Readers and **PII readers** live in `port.yaml`, next to the data. `dpb generate` writes the views and grants, and a column with personal data shows NULL to everyone but PII readers |
| No promise | Each output port promises a **freshness**, and each table has **quality rules** that run after every build |
| Every team names things its own way | Naming templates and settings apply to every data product, and `dpb validate` checks them in CI |

[How it works](concepts.md) describes each of these in detail, and the [tutorial](tutorial.md) builds two data products step by step.

## Three kinds of data product

Every data product has a **kind**. datapatchbay ships three, which are the usual ones in data mesh:

Source-aligned
: Publishes the data of one source system, cleaned and described, but not reshaped. Example: the orders of the shop's order system. Its prefix is `sa`.

Aggregate
: Combines or summarises other data products into a concept that more than one reader needs. Example: the turnaround time of orders. Its prefix is `agg`.

Consumer-aligned
: Shapes data for one use, such as a report, a dashboard or the input of a model. Its prefix is `ca`.

A kind is a label. It gives the data product its prefix, and it does not restrict what a data product may read. A team can rename the kinds or add its own in the [settings](files.md#datapatchbayyaml).

## Where the idea comes from

Zhamak Dehghani named data as a product as one of the four principles of **data mesh**. datapatchbay applies them to one team or a few teams on one warehouse:

Domain ownership
: The business domain that knows the data owns it, not a central team that only moves it. In datapatchbay every data product has a domain and an owner, written as free text, with no team registry to fill in first.

Data as a product
: Each domain publishes its data as products that others can find, understand and trust. In datapatchbay `dpb list` and `dpb describe` show every data product, table files describe every table and column, and output ports are views over private tables.

Self-serve data platform
: A platform team gives domains the tools to build and run data products without becoming a bottleneck. In datapatchbay `dpb new` scaffolds a data product in minutes, and `dpb generate` writes the orchestrator files and the warehouse SQL. The platform is the orchestrator and warehouse a team already runs.

Federated computational governance
: Global rules, such as naming, access and personal data, are agreed together and enforced by code, not by review meetings. In datapatchbay naming templates, settings with defaults and `dpb validate` in CI enforce the shared rules on every pull request.

Most of the books below describe a large company. datapatchbay leaves out what such a company adds: a web marketplace, catalog search across the company, and live measurement of freshness. See the [roadmap](roadmap.md) and [Limits and guarantees](limits.md).

## Further reading

Books:

- Zhamak Dehghani, *Data Mesh: Delivering Data-Driven Value at Scale*. O'Reilly, 2022. The source of the four principles and of the characteristics of a data product.
- Andrea Gioia, *Managing Data as a Product: Design and build data-product-centered socio-technical architectures*. Packt, 2024. Designing, building and running data products across their lifecycle, with a self-serve platform.
- Jean-Georges Perrin and Eric Broda, *Implementing Data Mesh: Principles and Practice to Design, Build, and Implement Data Mesh*. O'Reilly, 2024. A practical path from the principles to working data products and data contracts.
- Jacek Majchrzak, Sven Balnojan and Marian Siwiak, with Mariusz Sieraczkiewicz, *Data Mesh in Action*. Manning, 2023. Finding domains and growing a first data product into a mesh, step by step.
- Chad Sanderson and Mark Freeman, *Data Contracts: Developing Production-Grade Pipelines at Scale*. O'Reilly, 2025. Expectations of the data, ownership and enforcement in CI, close to what a table file and `dpb validate` do.
- Andrew Jones, *Driving Data Quality with Data Contracts*. Packt, 2023. Data contracts as the interface between the producer and the consumers of data.

Articles:

- Zhamak Dehghani, [How to Move Beyond a Monolithic Data Lake to a Distributed Data Mesh](https://martinfowler.com/articles/data-monolith-to-mesh.html). martinfowler.com, 2019. The article that introduced data mesh.
- Zhamak Dehghani, [Data Mesh Principles and Logical Architecture](https://martinfowler.com/articles/data-mesh-principles.html). martinfowler.com, 2020. The four principles, in short.

[Why not just dbt](alternatives.md) compares datapatchbay with dbt, a medallion architecture and the specifications that describe a data product or a contract in a file.
