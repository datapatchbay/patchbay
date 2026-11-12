# DuckDB enforces no access

On DuckDB, the view of an output port always shows NULL in a PII column. Readers and PII readers are accepted in the files and applied to nothing: the DuckDB warehouse creates no roles and no grants. The DuckDB warehouse enforces no access, and it is meant for local development and tests. We chose this so that the same files work on both warehouses and a team can develop on DuckDB and deploy on Postgres by changing one setting. The mistake that remains possible is hiding too much, never showing too much.

On Postgres the access policy of an output port becomes grants to roles and a view that shows a PII column only to members of a PII reader role (ADR-0002, ADR-0007, ADR-0017). DuckDB has no roles and no grants: whoever opens the database reads everything, the private schema included (ADR-0020).

## Considered options

- **The view shows the value of a PII column.** Rejected: nothing would be masked, so a port on DuckDB would show personal data to everyone, and a copy of the database made for development could leak it.
- **`dpb validate` fails on a PII column or a PII reader when the warehouse is DuckDB.** Rejected: the same files would not work on both warehouses, which was the reason to have DuckDB next to Postgres.
- **Accept readers and let `dpb validate` warn that DuckDB enforces no access.** Rejected: the warning would repeat on every run for every team that develops on DuckDB, and the docs already say it once.

## Consequences

- A test on DuckDB cannot show that a PII reader sees a PII value, or that a reader without access is refused. Those checks stay integration tests on Postgres (ADR-0020).
- A team that needs to see PII values while developing cannot do so through an output port on DuckDB. It reads the private schema, which DuckDB does not protect.
- `dpb validate` treats readers and PII readers the same on both warehouses, so a wrong reader is still caught before deploying on Postgres.
