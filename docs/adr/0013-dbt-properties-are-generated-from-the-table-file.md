# dbt properties are generated from the table file

A team chooses per data product, or per table, whether Python or dbt builds a table. Either way the table's contract lives in datapatchbay's table file (ADR-0003). For a table built by dbt, `dpb generate` writes the dbt properties of that model from the table file: its description, its columns with their types, the quality rules as dbt data tests with their severity, an enforced dbt model contract, the model's alias and schema, and the dbt group of its data product. The team writes the model's SQL and nothing else about it. We chose this because the definitions of a data product belong in one place that does not depend on the executor, and a dbt team should not maintain the same columns and tests twice.

The table file has the same shape as dbt's properties, so a dbt user recognises it: a list of columns with a name, a type and a description, and rules written as a bare name or a name with arguments. It keeps datapatchbay's words (`type`, `rules`, `warning`) instead of dbt's (`data_type`, `data_tests`, `warn`), because the files are meant to be read by domain experts and the glossary avoids "test". The generated properties use dbt's words.

The generated dbt properties are committed, unlike the generated DAG files, because dbt reads them on every run: on a fresh clone, in dbt Cloud and in editor tooling. They sit next to the model, and `dpb validate` fails when they differ from what the table file produces.

## Considered options

- **The contract lives in dbt and `dpb` reads it from the manifest.** Rejected: the definition of a data product would then depend on which executor builds it, and changing executor would mean moving the contract.
- **Both declare it and `dpb validate` checks that they match.** Rejected: two copies to keep in step by hand.
- **dbt's words in the table file.** Rejected: three words of familiarity for dbt users against a file that reads as test configuration to everyone else.
- **Generated dbt properties are build output and not committed.** Rejected: `dbt build` on a fresh clone would fail until someone ran `dpb generate`.

## Consequences

- A dbt properties entry written by hand for a model that a table file builds is a duplicate, and `dpb validate` fails on it.
- A team with an existing dbt project ports it once: each model's SQL moves into the folder of the data product that owns it (ADR-0015), and its properties move into table files, for example with an import command.
- The enforced dbt model contract makes dbt itself check at build time that the model produces the declared columns and types.
- For a table built by dbt, the quality rules run as dbt data tests during the dbt build, not as separate generated audit tasks. This narrows ADR-0010 to executors without their own tests.
- A table built by dbt needs no `needs` list: the order comes from the model's `ref()` calls.
