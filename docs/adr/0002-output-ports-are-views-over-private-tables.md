# Output ports are views over private tables

The executor builds every output table in the data product's private schema. An output port holds only generated views over those tables, and readers are granted access to the views, never to the tables. We chose this so that one rule covers every table: masking of personal data happens in the view, where a PII column shows its value to PII readers and NULL to everyone else, and both groups query the same object.

## Considered options

- **Views only for tables with PII columns.** Rejected: the executor would have to write to a different schema depending on whether a table has a PII column, and adding the first PII column would move the table.
- **Column-level grants instead of views.** Rejected: `SELECT *` fails for readers without access to every column.
- **A second schema of masked views per port.** Rejected: readers and PII readers would query different objects for the same table.

## Consequences

- Executor code never writes to an output port. It writes to the private schema, and the view makes the table visible.
- The view layer is the place where a later write-audit-publish step can switch readers from one build of a table to the next.
