# Settings cascade over packaged defaults

Every setting has a default that ships inside the package, in one file with the same shape as `datapatchbay.yaml`. A repo's `datapatchbay.yaml` holds only the changes: maps merge key by key, lists and single values replace. Below the root, executor, runtime, container image and default severity can be set on a data product, a port or a table, and the nearest one wins. `dpb config` and `dpb describe` show each resolved value and where it came from. We chose this so that a small team starts with a one-line root file and still can deviate for one table.

Orchestrator can be set at root or data product level only. One data product is one DAG, so two tables in it cannot use different orchestrators.

## Considered options

- **`dpb init` writes all defaults into the repo.** Rejected: a new default in a later release would not reach existing repos, and the file hides the few lines a team actually chose.
- **Lists merge instead of replace.** Rejected: a team could then not remove a default kind or domain.

## Consequences

- A change to a packaged default changes the behaviour of every repo that did not set that value. Such a change is a breaking change and needs a schema version bump (see ADR-0011).
- The packaged defaults of a plugin that declares settings ship with that plugin and are merged under the repo's file in the same way, with the origin `defaults of plugin <name>`. They do not cascade below the root (ADR-0025).
