# The `dpb` CLI

| Command | What it does |
| --- | --- |
| `dpb new` | Scaffolds a product folder that already follows the conventions |
| `dpb check` | Validates every product against the conventions and its contract. Meant for CI |
| `dpb list` | Shows all products with their domain and owner |
| `dpb describe` | Prints one product's contract, for humans or agents |
| `dpb deploy` | Creates schemas, runs the transformation for one environment, and applies grants |
| `dpb export` | Writes the contract in another format, such as Cube or a public data product spec |

## Built for agents

The CLI is designed to be driven by AI agents as well as people:

- Every command has `--json` output.
- Every command accepts YAML or JSON on standard input.
- A non-interactive mode fails instead of prompting.
- A published JSON schema lets an agent validate a file before writing it.

An MCP server may come later, if the CLI turns out not to be enough.

## Where it runs

- **In pull requests.** The users are engineers, and the product is the set of conventions. Approvals happen in pull requests, which every team already has.
- **In CI.** `dpb check` validates every product on each change.
- **From your orchestrator.** datapatchbay has no scheduler. Airflow, Dagster or cron call `dpb deploy`.
