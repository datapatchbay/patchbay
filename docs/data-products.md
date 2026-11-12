# Data products

The idea behind datapatchbay on one page: what a data product is, where the idea comes from, how `dpb` puts it into files, and what to read next.

## Data as a product

A table that a pipeline writes as a side effect has no owner, no promise and no interface. Whoever needs it joins straight into it, and every change breaks someone. Treating data as a product turns that around. A team publishes data for others on purpose, the way a team publishes an API:

- It has an **owner** who is accountable for it.
- It has **consumers**, and the owner knows who they are.
- It has an **interface** that stays stable while the inside changes.
- It makes **promises**, such as a schema, quality rules and freshness, and keeps them.

A **data product** is the unit that carries all of this: the data, the code that builds it, the metadata that describes it and the policies that guard it, owned together.

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

## How datapatchbay addresses this

datapatchbay does not replace dbt or the layers. It cuts the platform vertically into data products, and keeps the layers inside each one:

| Problem | What datapatchbay does |
| --- | --- |
| Everything is public | Build code writes to the data product's **private schema**. Consumers read only the views of an **output port**, so the inside can change freely |
| Nobody owns a table | Every data product names an **owner**, and `dpb validate` fails without one. A **technical owner** can be named next to it |
| Unknown consumers | A reading data product must be listed in the **readers** of the output port, so the owner approves every new consumer in a pull request |
| Access by hand | Readers and **PII readers** live in `port.yaml`, next to the data. `dpb generate` writes the views and grants, and a PII column shows NULL to everyone but PII readers |
| No promise | Each output port promises a **freshness**, and each table has **quality rules** with a severity that run after every build |
| Opt-in conventions | Naming templates and settings apply to every data product, and `dpb validate` checks them in CI |
| Only dbt is covered | Python and dbt build code sit side by side, per table. Ingestion, dbt models and consumers are in one model |

The layers map onto a data product as follows: bronze and silver are its private schema, and gold is its output port. The difference is that each data product has its own gold, with its own owner, readers and promises.

dbt stays the build tool where a team wants it. For a table built by dbt, `dpb generate` writes the dbt properties from the table file: an enforced model contract, the quality rules as data tests, a dbt group with the owner, and a `source()` for every output port the data product reads. See [Build a table with dbt](howto/dbt.md).

## Where the idea comes from

Zhamak Dehghani named data as a product as one of the four principles of **data mesh**:

Domain ownership
: The business domain that knows the data owns it, not a central team that only moves it.

Data as a product
: Each domain publishes its data as products that others can find, understand and trust.

Self-serve data platform
: A platform team gives domains the tools to build and run data products without becoming a bottleneck.

Federated computational governance
: Global rules, such as naming, access and personal data, are agreed together and enforced by code, not by review meetings.

Dehghani also lists what makes a data product usable. It is **discoverable**, **addressable**, **understandable**, **trustworthy**, **natively accessible**, **interoperable**, **valuable on its own** and **secure**.

## How datapatchbay maps the idea

datapatchbay applies the idea to one team or a few teams on one warehouse. Most of the books below describe a large company. Here, a data product is a folder of YAML files in a repo, and pull requests carry the approvals.

| Characteristic | In datapatchbay |
| --- | --- |
| Owned | `dataproduct.yaml` names an owner, a technical owner and a domain |
| Discoverable | `dpb list` and `dpb describe` show every data product, with `--json` for tools and agents |
| Addressable | Naming templates give every port a name that is unique across the repo |
| Understandable | Table files describe each table and column, and the contract names no technology |
| Trustworthy | Quality rules with a severity run after each build. Each output port promises a freshness, and `dpb validate` checks it against the inputs |
| Natively accessible | An output port is a schema of views in the warehouse, so SQL, BI tools and dbt read it as they are |
| Interoperable | Input ports read other output ports. A dbt model reads them through a generated `source()` |
| Secure | Each output port lists its readers and PII readers, and the generated grants apply them. The owner approves every new reader in a pull request |
| Valuable on its own | Not something a tool can check. The data product kind and the owner's judgment carry it |

The four principles map as follows:

- **Domain ownership.** Every data product has a domain and an owner, written as free text, with no team registry to fill in first.
- **Data as a product.** Output ports are views over private tables. Consumers see the interface and never the inside.
- **Self-serve platform.** `dpb new` scaffolds a data product in minutes, and `dpb generate` writes the Airflow DAGs and warehouse SQL. The platform is the orchestrator and warehouse a team already runs.
- **Computational governance.** Naming templates, settings with defaults and `dpb validate` in CI enforce the shared rules on every pull request.

What datapatchbay leaves out is listed in the [roadmap](roadmap.md): a web marketplace, catalog search across the company, and live measurement of freshness. [How it works](concepts.md) describes the model in detail.

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

Specifications that describe a data product or a contract in a file are compared with datapatchbay in [Alternatives](alternatives.md).
