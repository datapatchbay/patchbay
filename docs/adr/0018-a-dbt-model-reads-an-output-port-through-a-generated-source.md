# A dbt model reads an output port through a generated source

A dbt model in one data product reads a table of another data product's output port with `source('<port>', '<table>')`. For each input port that reads another data product's output port, `dpb generate` writes one dbt source into `models/_sources.yml` of the reading data product. ("Source" here is dbt's word for a declared table; it is not the glossary's source, a system outside the platform.) The source is named after the port, points at the output port's schema, and lists the producer's tables with their columns, taken from the producer's table files. The file is committed with the other generated dbt files (ADR-0013). We chose this because it works whatever executor builds the producer, and because it leaves `ref()` with one meaning: a `ref()` into a model of another data product is always a read of a private table, so the check of ADR-0014 can tell the two apart from the manifest alone.

The source follows the input port, so a model can only name a source that the data product declared (and, by ADR-0007, was approved to read). Only the contract is copied: table names and columns with their descriptions. Quality rules, freshness and access stay on the producer's output port.

## Considered options

- **Generate each output port's views as dbt models, so that `ref()` works.** Rejected: it works only when dbt builds the producer. A dbt model would also have to be generated for a view that the warehouse plugin already creates (ADR-0002), and `ref()` would no longer tell a port read from a private read.
- **Teams write the sources by hand.** Rejected: the list of tables and columns would be a second copy of the producer's table files, to keep in step by hand.

## Consequences

- `dpb validate` fails when the committed sources differ from what the table files produce, as it does for the other generated dbt files.
- A `ref()` that resolves to a model of another data product is a read of a private table. `dpb validate` fails on it (ADR-0014, case 1).
- A `source()` that is not one of the generated ones, or whose port the data product has no input port on, fails the check of ADR-0014.
- Source names are unique in a dbt project, and several data products can read one output port. The source of a port is therefore written once, in `models/_sources.yml` of the first reading data product built by dbt, in name order, and every reader uses it.
- A producer built by Python and one built by dbt are read the same way.
