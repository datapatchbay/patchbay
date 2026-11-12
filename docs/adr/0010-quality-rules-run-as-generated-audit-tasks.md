# Quality rules run as generated audit tasks

Because `dpb` never connects to the warehouse (ADR-0001), quality rules cannot run inside `dpb`. Each rule is turned into SQL by the warehouse plugin and runs in a generated audit task after the table's build task, through the orchestrator's connection. Each rule has a severity: `error` fails the run, `warning` reports and continues, `none` skips the rule. We chose this so that the rules in the contract are enforced from the first release, with no extra tool for a team to install.

## Considered options

- **Rules declared only, enforced by the executor's own code.** Rejected: every team would write the same checks again, and the contract would promise what nothing verifies.
- **Wait for write-audit-publish.** Rejected: it postpones all enforcement to milestone 2.

## Consequences

- In milestone 1 the audit runs after the table is built, so a failed rule stops the run but the data is already visible through the output port's view. Write-audit-publish in milestone 2 closes this gap.
- The audit logic is part of the generated DAG file, since that file may not import datapatchbay.
