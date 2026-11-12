# Owners and column types are free text

`owner` and `technical_owner` name a person as free text, and a column's `type` is written as the warehouse spells it. `dpb validate` checks that they are present and nothing more. We chose this to keep the five-minute start: no registry of people or teams to fill in first, and no type system to learn or to map to each warehouse.

## Considered options

- **Owner is a team declared in a root registry.** Rejected: a person is the name to call when a number is wrong, and a registry is one more file before the first data product exists.
- **A closed set of logical column types mapped per warehouse.** Rejected: it limits teams to the types datapatchbay knows and needs a mapping for every warehouse plugin.

## Consequences

- When a person leaves, their data products keep a stale owner until someone edits the files. `dpb list` makes this visible; nothing enforces it.
- Checks that depend on a column's type, such as naming rules for timestamps, are not possible (see ADR-0006).
- The same contract cannot move between warehouses without editing column types.
