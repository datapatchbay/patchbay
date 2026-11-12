# datapatchbay

**Data products as code.** Declare owners, ports and freshness in YAML, then scaffold, check and deploy from one lightweight CLI.

datapatchbay is a file-based CLI that turns a data platform into a set of owned data products. Each product is a folder with a few YAML files. They state who owns it, what it reads, what it publishes, how fresh each output is, and who may read it. The CLI scaffolds those folders, validates them in CI and applies them to the warehouse.

The name comes from the patchbay behind a mixing console. Every input and output has a labelled jack, and you route signals by declaring connections.

The command is `dpb`, and the project is licensed under Apache 2.0.

## The problem

Small and mid-size data teams hit the same four issues once more than one person or domain is involved:

- **Nobody owns a table.** When a number is wrong, there is no name to call.
- **Everything is public.** Consumers join straight into intermediate tables, so every refactor breaks a report.
- **The same concept has several names.** One department says *order*, another says *test*, a third says *analysis*, and each gets a different count.
- **Access is handled by hand,** usually by putting people in a BI group. So nobody can safely query the warehouse directly, and neither can an AI agent.

Data mesh gave teams the vocabulary for this but no implementation. The existing specifications are large YAML schemas with no workflow attached, and a team of two has no idea where to start. The goal here is that creating a data product takes five minutes.

## Who it is for

- A central data team on a single platform that wants ownership and contracts without buying a catalog.
- A company where a second or third team starts building on the same warehouse.
- Teams of 2 to 20 engineers. Larger organisations with a governance department are better served by a portal.

## First milestone

One two-person data team, one source system, and two products running in production with `dpb check` in CI.

- **The test for the contract:** a domain expert who does not write code can read a product file and confirm it.
- **The test for the CLI:** the engineer can run it without reading the docs.

```{toctree}
:hidden:

concepts
cli
design
alternatives
```
