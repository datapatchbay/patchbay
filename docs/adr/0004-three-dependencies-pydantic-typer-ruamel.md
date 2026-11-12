# Three dependencies: Pydantic, Typer and ruamel.yaml

datapatchbay aims to be lightweight, yet it depends on Pydantic and Typer instead of the standard library alone. We accepted them because Pydantic gives validation and the published JSON Schema from one set of models, and Typer gives the CLI with little code. Writing both by hand would be more code to maintain than the dependencies cost. Nothing else is added: no database driver (see ADR-0001) and no template engine, so generated files are built from plain strings.

ruamel.yaml is the only YAML library. `dpb upgrade` rewrites a team's files and must keep their comments and key order, which PyYAML cannot do. ruamel.yaml also gives line numbers for error messages and reads `no` and `on` as text.

## Considered options

- **PyYAML only, with dataclasses and argparse.** Rejected: an in-house validator and JSON Schema generator to write and maintain.
- **msgspec and PyYAML.** Rejected: it stops at the first error and gives no line numbers.
- **PyYAML next to ruamel.yaml.** Rejected: two libraries that can read the same file differently.
