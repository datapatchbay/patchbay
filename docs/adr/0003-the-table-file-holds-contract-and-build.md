# The table file holds both the contract and the build

The original design kept every technology out of the data product files and put "how it runs" in a separate runner section. We decided instead that a table file has two parts: the contract (columns, quality rules), which names no technology, and a `build` block (executor, entrypoint, parameters, the tables it needs), which does. One file per table keeps what a table promises next to how it is made, and the generated DAG needs the build facts per table anyway.

The rule that survives is narrower: the contract part never names a technology, and the build block can be swapped without touching the contract.

## Considered options

- **A separate build file next to each table file.** Rejected: twice the files for the same table, and the two must be kept in sync by name.
