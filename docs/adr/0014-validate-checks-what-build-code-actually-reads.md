# dpb validate checks what build code actually reads

Input ports declare what a data product reads, but the build code is what really reads. `dpb validate` compares the two and fails when a table's build code:

1. reads a table in another data product's private schema,
2. reads another data product's output port without an input port on it, or
3. reads an output port whose readers do not include its data product (ADR-0007).

The executor plugin reports what each table's build code reads. The rules themselves live once in the core, so every executor gets the same checks. For dbt, the reads come from the `ref()` and `source()` dependencies in the dbt manifest, which CI produces with `dbt parse` before `dpb validate` runs. We chose this because ports are only real if the code respects them: in a single dbt project one role builds every model, so warehouse grants (ADR-0002) do not stop one data product's model from reading another's private table while it builds.

## Considered options

- **Rely on warehouse grants alone.** Rejected: grants separate readers, not data products that share a build role, and a leak would only show up when someone changes the role setup.
- **Rely on dbt's group access.** Rejected as the only check: it covers dbt alone, it does not know about input ports or readers, and the rules would have to be written again for every executor.

## Consequences

- `dpb validate` needs an up-to-date dbt manifest for data products built by dbt. Reading it is reading a file; ADR-0001 still holds.
- An executor that cannot report its reads, such as Python, gets no code check. For those, the warehouse is the only enforcement, which works only if each build runs as its data product's role.
- A table name hard-coded in SQL instead of a `ref()` or `source()` is invisible to the check.
