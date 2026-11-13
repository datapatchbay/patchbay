# Plugins declare their own settings and naming templates

Any plugin, of any of the four extension points, may declare settings of its own through an optional capability protocol, `DeclaresSettings`, in `datapatchbay.plugins` (like the executor capabilities of ADR-0024, the core asks with `isinstance` and never by name). A plugin declares:

- a **section** at the root of `datapatchbay.yaml`, named after the plugin's entry point name: a pydantic model with a description for every key, and the defaults. A section is read at the root only and does not cascade.
- **naming templates** under `conventions.names`, each with a default, a description and the placeholders it may use besides `{name}`, `{kind.prefix}` and `{kind.name}`.

The core builds the model of `datapatchbay.yaml` from the core settings and from what the installed plugins declare, so one model validates the file and generates `dpb schema root`. It merges the defaults of the plugins into the packaged defaults, in the same cascade of ADR-0008, and hands the resolved section of each plugin to the plans (`plugin_settings`, by plugin name). `dpb config` shows these settings with the origin `defaults of plugin <name>`, or `datapatchbay.yaml` when the repo sets them. The `dbt:` block (`project_dir`, `profiles_dir`, `manifest`) and the `dbt_model` naming template are the first users: they stay exactly where users write them, the file format does not change and `schema_version` stays 1, but their models, defaults and placeholders now live in `integrations/dbt`, and neither `defaults.yaml` nor `models/root.py` names dbt. `DbtLocation` and the dbt-specific part of the table plan moved into the dbt integration too.

We chose this so that a new technology brings its configuration with it, in one folder (ADR-0024), instead of the core growing a root key for every plugin, and so that a third-party plugin has the same powers as a built-in one.

## Considered options

- **A free-form `plugins:` map in the root file.** Rejected: the settings would be unchecked and out of the JSON Schema, and the `dbt:` block would have to move, which is a breaking change to every repo that sets it.
- **Keep the `dbt:` block in the core as a documented exception.** Rejected: the core would name a technology, and the next plugin with settings would ask for the same exception.
- **Let a section cascade to data products, ports and tables.** Rejected for now: nothing needs it. The cascade of ADR-0008 stays for `executor`, `runtime`, `image`, `container` and `severity`.

## Consequences

- A root key is valid when it is a core setting or the section of an installed plugin. Any other key fails `dpb validate` as an unknown key (ADR-0011) and says that no installed plugin declares a settings section of that name. A repo with a `dbt:` block therefore needs the `dbt` plugin installed, which it always is with datapatchbay.
- The validity of `datapatchbay.yaml` and the output of `dpb schema root` now depend on the installed plugins. `dpb schema root` is the same as before when the built-in plugins are the only ones.
- The registry refuses a plugin whose name is a root setting (`runtime`, `conventions`, ...), whose section another plugin declares too, or whose naming template collides with a core one or another plugin's, and a section whose defaults its own model rejects. The error stops the command with exit code 2, before any file is read as valid.
- Packaged defaults are no longer in one file: those of a plugin ship with the plugin. ADR-0008 holds as it was: the packaged defaults, wherever they ship, are merged under the repo file, and changing one is a breaking change that needs a schema version bump. The position of the settings in `dpb config` is unchanged: sections before `conventions`, templates last in `conventions.names`.
- For existing repos nothing changes: the same files validate, the generated files are byte-identical, and `dpb config` differs only in the origin label of the dbt settings (`defaults of plugin dbt`).
- The integration boundary of ADR-0024 is tighter: the only dbt left in the core is `dpb new --from-dbt` and prose.
