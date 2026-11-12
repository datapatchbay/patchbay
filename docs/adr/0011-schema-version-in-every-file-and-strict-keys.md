# Schema version in every file, strict keys, upgrade from the first release

Each of the four kinds of file carries `schema_version`. Unknown keys fail validation, and every file accepts a free-form `meta` map for a team's own extras. `dpb upgrade` ships in milestone 1 with the machinery for rewriting files while keeping comments, although there is no migration to run yet. We chose strict keys so that a typo such as `ownr` is caught instead of ignored, and we ship `upgrade` early so that the first breaking change does not also have to invent the way out.

The version goes up only for breaking changes. A new optional key does not count.

## Considered options

- **Version in `datapatchbay.yaml` and `dataproduct.yaml` only.** Rejected: a port or table file copied between repos would not say which schema it follows.
- **Unknown keys produce a warning.** Rejected: warnings are ignored, and the `meta` map already gives room for extras.
- **`dpb upgrade` together with the first breaking change.** Rejected: a team that hits its first breaking change should already know the command.

## Consequences

- An older `dpb` rejects a file that uses a newer optional key. The error must say that the key may come from a newer release.
- `dpb` refuses files with a `schema_version` newer than it knows.
- The root keys that are valid depend on the installed plugins: a plugin may declare a section named after itself (ADR-0025). A root key that no installed plugin declares is an unknown key, and the message says so. Adding a section to a plugin is a new optional key, so it does not bump the version.
