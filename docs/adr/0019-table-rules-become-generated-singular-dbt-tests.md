# Table rules become generated singular dbt tests

The column rules `not_null`, `unique` and `accepted_values` map to dbt's built-in generic data tests (ADR-0013). The table rules `primary_key`, `row_count` and `sql` have no built-in equivalent. For a table built by dbt, `dpb generate` writes each of them as a singular dbt data test: one SQL file per rule, in the `tests/` folder of the data product, beside its `models/` folder, and committed like the dbt properties. The SQL selects the rows that break the rule, so the test passes when it returns none, which is also how a `sql` rule is written. We chose this because it needs no dbt package installed, and because the generated files stay self-contained, as the generated DAGs do (ADR-0001).

Severity maps as it does for column rules: a rule's own severity, or else the table's, and then `error` becomes `error`, `warning` becomes `warn`, and `none` writes no test. The generated file sets it with `config(severity=...)`.

## Considered options

- **Generic tests from `dbt_utils`.** Rejected: the team would have to install a dbt package, and its version would become part of the contract.
- **dbt model constraints for `primary_key`, and one of the above for the rest.** Rejected: constraints are not enforced on every warehouse, and they cannot carry a severity, so a `primary_key` with severity `warning` could not be expressed.

## Consequences

- A table with table rules needs no dbt package, and `dpb validate` stops rejecting these rules on a table built by dbt once the mapping is generated.
- `dpb generate` also keeps the `test-paths` of `dbt_project.yml` in step with the data product folders, changing only that key, as it does for `model-paths` (ADR-0015).
- The file for a rule is named `<dbt_model>__<rule>.sql`. Further rules of the same kind (for example a second `sql` rule) in one table file get a suffix `_2`, `_3` in file order. Test names must be unique across a dbt project, which the dbt model name already guarantees.
- A `sql` rule is copied as written, so it names the model with `ref()`; that is a read inside its own data product, and ADR-0014 accepts it.
